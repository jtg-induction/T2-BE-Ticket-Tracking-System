import base64
import binascii
import hashlib
import json
import re

from Crypto.Cipher import AES
from django.conf import settings
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.constants import PAGE_SIZE


def get_aes_key():
    """
    Derives a 256-bit AES key from the Django SECRET_KEY.
    Returns:
        bytes: A 32-byte hash to be used as an encryption key.
    """
    raw_key = settings.ENCRYPTION_KEY.encode()
    return hashlib.sha256(raw_key).digest()


def encrypt_token(raw_token):
    """
    Encrypts a string using AES-GCM and returns a base64 encoded JSON package.
    """
    if not raw_token:
        return None

    key = get_aes_key()
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(raw_token.encode())

    package = {
        "nonce": base64.b64encode(cipher.nonce).decode(),
        "tag": base64.b64encode(tag).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }
    return base64.b64encode(json.dumps(package).encode()).decode()


def decrypt_token(encrypted_token):
    """
    Decrypts a base64 encoded AES-GCM package.
    """
    if not encrypted_token:
        return None

    try:
        key = get_aes_key()
        raw_data = base64.b64decode(encrypted_token).decode()
        package = json.loads(raw_data)

        nonce = base64.b64decode(package["nonce"])
        tag = base64.b64decode(package["tag"])
        ciphertext = base64.b64decode(package["ciphertext"])

        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()
    except (
        KeyError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ):
        return None


class StandardizedPagination(PageNumberPagination):
    page_size = PAGE_SIZE
    page_size_query_param = "page_size"

    def get_paginated_response(self, data):
        """
        Formats the pagination metadata for standardized_response.
        """
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


def parse_jira_error(e):
    """
    Handles DRF ErrorDetail lists and extracts clean Jira error strings.
    """
    if isinstance(e, list) and len(e) > 0:
        e = e[0]

    raw_text = str(e)

    try:
        json_match = re.search(r"\{.*\}", raw_text)

        if json_match:
            json_str = json_match.group()
            json_str = json_str.replace("\\'", "'").replace('\\"', '"')

            error_data = json.loads(json_str)

            messages = []

            field_errors = error_data.get("errors", {})
            if isinstance(field_errors, dict):
                messages.extend(field_errors.values())

            general_messages = error_data.get("errorMessages", [])
            if isinstance(general_messages, list):
                messages.extend(general_messages)

            if messages:
                return " ".join(str(m) for m in messages)

    except Exception:
        pass

    clean_fallback = re.sub(r"ErrorDetail\(string='|', code='.*'\)", "", raw_text)
    return clean_fallback.strip("[]' ")


class ADFConverter:
    """
    A utility class to convert Markdown-style text into Atlassian Document Format (ADF).

    This converter handles block-level elements (Headings, Paragraphs) and
    inline-level formatting (Bold, Italic, Strikethrough, Code, and Links).
    """

    @staticmethod
    def to_adf(text):
        """
        Converts a string of Markdown text into a full ADF JSON structure.

        Args:
            text (str): The raw markdown string to convert.

        Returns:
            dict: A dictionary representing the ADF 'doc' root, or None if input is empty.
        """
        if not text:
            return None

        lines = text.split("\n")
        content_nodes = []

        for line in lines:
            if not line.strip():
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
            if heading_match:
                hashes, content = heading_match.groups()
                content_nodes.append(
                    {
                        "type": "heading",
                        "attrs": {"level": len(hashes)},
                        "content": ADFConverter._parse_inline(content),
                    }
                )
                continue

            content_nodes.append(
                {"type": "paragraph", "content": ADFConverter._parse_inline(line)}
            )

        return {"version": 1, "type": "doc", "content": content_nodes}

    @staticmethod
    def _parse_inline(text):
        """
        Parses a single line of text into ADF inline nodes with marks.

        Identifies code snippets, bold text, italics, strikethroughs, and
        hyperlinks using regular expressions.

        Args:
            text (str): The line content to be parsed for inline formatting.

        Returns:
            list: A list of ADF text nodes containing text and associated marks.
        """
        pattern = r"(`(?P<code>[^`]+)`)|(\*\*(?P<bold>[^*]+)\*\*)|(\*(?P<italic>[^*]+)\*)|(~~(?P<strike>[^~]+)~~)|(\[(?P<text>[^\]]+)\]\((?P<url>[^\)]+)\))"

        nodes = []
        last_idx = 0

        for match in re.finditer(pattern, text):
            if match.start() > last_idx:
                nodes.append({"type": "text", "text": text[last_idx : match.start()]})

            groups = match.groupdict()
            if groups["code"]:
                nodes.append(
                    {
                        "type": "text",
                        "text": groups["code"],
                        "marks": [{"type": "code"}],
                    }
                )
            elif groups["bold"]:
                nodes.append(
                    {
                        "type": "text",
                        "text": groups["bold"],
                        "marks": [{"type": "strong"}],
                    }
                )
            elif groups["italic"]:
                nodes.append(
                    {
                        "type": "text",
                        "text": groups["italic"],
                        "marks": [{"type": "em"}],
                    }
                )
            elif groups["strike"]:
                nodes.append(
                    {
                        "type": "text",
                        "text": groups["strike"],
                        "marks": [{"type": "strike"}],
                    }
                )
            elif groups["text"]:
                nodes.append(
                    {
                        "type": "text",
                        "text": groups["text"],
                        "marks": [{"type": "link", "attrs": {"href": groups["url"]}}],
                    }
                )

            last_idx = match.end()

        if last_idx < len(text):
            nodes.append({"type": "text", "text": text[last_idx:]})

        return nodes if nodes else [{"type": "text", "text": text}]


class ADFToMarkdownConverter:
    """
    A utility class to convert Atlassian Document Format (ADF) JSON back into Markdown text.
    """

    @staticmethod
    def to_markdown(adf_data):
        """
        Converts an ADF dictionary into a Markdown string.

        Args:
            adf_data (dict): The full ADF 'doc' structure.

        Returns:
            str: The converted Markdown string.
        """
        if not adf_data or "content" not in adf_data:
            return ""

        markdown_parts = []
        for node in adf_data["content"]:
            markdown_parts.append(ADFToMarkdownConverter._process_node(node))

        return "\n\n".join(markdown_parts)

    @staticmethod
    def _process_node(node):
        """
        Processes individual ADF nodes (headings, paragraphs, text) into Markdown.
        """
        node_type = node.get("type")
        content = node.get("content", [])

        inner_text = ""
        for child in content:
            inner_text += ADFToMarkdownConverter._process_inline_node(child)

        if node_type == "heading":
            level = node.get("attrs", {}).get("level", 1)
            return f"{'#' * level} {inner_text}"

        if node_type == "paragraph":
            return inner_text

        if node_type == "rule":
            return "---"

        return inner_text

    @staticmethod
    def _process_inline_node(node):
        """
        Handles text nodes and applies Markdown symbols based on ADF marks.
        """
        if node.get("type") != "text":
            return ""

        text = node.get("text", "")
        marks = node.get("marks", [])

        for mark in marks:
            mark_type = mark.get("type")
            if mark_type == "strong":
                text = f"**{text}**"
            elif mark_type == "em":
                text = f"*{text}*"
            elif mark_type == "strike":
                text = f"~~{text}~~"
            elif mark_type == "code":
                text = f"`{text}`"
            elif mark_type == "link":
                url = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({url})"

        return text
