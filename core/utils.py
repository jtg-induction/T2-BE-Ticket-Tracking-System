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
    A converter to transform Markdown-style text into Atlassian Document Format (ADF).
    """

    @staticmethod
    def to_adf(text):
        """
        Converts a Markdown string into an ADF dictionary structure.
        """
        if not text:
            return None

        lines = text.split("\n")
        content_nodes, list_buffer, list_type = [], [], None

        def flush_list():
            if list_buffer:
                content_nodes.append({"type": list_type, "content": list_buffer[:]})
                list_buffer.clear()

        for line in lines:
            stripped_line = line.lstrip()

            bullet_match = re.match(r"^[\*\-\+]\s+(.*)", stripped_line)
            order_match = re.match(r"^\d+\.\s+(.*)", stripped_line)

            if bullet_match or order_match:
                new_type = "bulletList" if bullet_match else "orderedList"
                if list_type and new_type != list_type:
                    flush_list()

                list_type = new_type
                content = (
                    bullet_match.group(1) if bullet_match else order_match.group(1)
                )

                list_buffer.append(
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": ADFConverter._parse_inline(content),
                            }
                        ],
                    }
                )
                continue

            if not stripped_line:
                flush_list()
                continue

            flush_list()

            heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped_line)
            if heading_match:
                hashes, content = heading_match.groups()
                content_nodes.append(
                    {
                        "type": "heading",
                        "attrs": {"level": len(hashes)},
                        "content": ADFConverter._parse_inline(content),
                    }
                )
            else:
                content_nodes.append(
                    {
                        "type": "paragraph",
                        "content": ADFConverter._parse_inline(line.strip()),
                    }
                )

        flush_list()
        return {"version": 1, "type": "doc", "content": content_nodes}

    @staticmethod
    def _parse_inline(text, active_marks=None):
        """
        Recursively parses inline text to identify marks like bold, italic, and links.
        """
        if not text:
            return []
        if active_marks is None:
            active_marks = []

        patterns = [
            (r"\*\*\*(.*?)\*\*\*", ["strong", "em"]),
            (r"\*\*(.*?)\*\*", ["strong"]),
            (r"~~(.*?)~~", ["strike"]),
            (r"\*(.*?)\*", ["em"]),
            (r"<u>(.*?)</u>", ["underline"]),
            (r"\+\+(.*?)\+\+", ["underline"]),
            (r"`(.*?)`", ["code"]),
            (r"\[(.*?)\]\((https?://[^\s\)]+)\)", ["link"]),
            (r"(https?://[^\s\)]+)", ["link_raw"]),
        ]

        for regex, mark_types in patterns:
            match = re.search(regex, text)
            if match:
                nodes = []
                if match.start() > 0:
                    nodes.extend(
                        ADFConverter._parse_inline(text[: match.start()], active_marks)
                    )

                new_marks = active_marks[:]
                inner_text = match.group(1)

                if "link" in mark_types:
                    new_marks.append(
                        {"type": "link", "attrs": {"href": match.group(2)}}
                    )
                elif "link_raw" in mark_types:
                    new_marks.append(
                        {"type": "link", "attrs": {"href": match.group(1)}}
                    )
                else:
                    for mt in mark_types:
                        if not any(m.get("type") == mt for m in new_marks):
                            new_marks.append({"type": mt})

                nodes.extend(ADFConverter._parse_inline(inner_text, new_marks))

                if match.end() < len(text):
                    nodes.extend(
                        ADFConverter._parse_inline(text[match.end() :], active_marks)
                    )
                return nodes

        return (
            [{"type": "text", "text": text, "marks": active_marks}]
            if active_marks
            else [{"type": "text", "text": text}]
        )


class ADFToMarkdownConverter:
    """
    A converter to transform Atlassian Document Format (ADF) JSON into Markdown text.
    """

    @staticmethod
    def to_markdown(adf_data):
        """
        Entry point to convert an ADF dictionary into a formatted Markdown string.
        """
        if not adf_data or "content" not in adf_data:
            return ""

        return ADFToMarkdownConverter._render_nodes(adf_data.get("content", [])).strip()

    @staticmethod
    def _render_nodes(nodes, indent_level=0):
        """
        Iterates through ADF nodes and recursively builds the Markdown string based on node types.
        """
        md = ""
        for node in nodes:
            node_type = node.get("type")

            if node_type == "heading":
                level = node.get("attrs", {}).get("level", 1)
                inner = ADFToMarkdownConverter._render_nodes(
                    node.get("content", []), indent_level
                )
                md += f"{'#' * level} {inner.strip()}\n\n"

            elif node_type == "paragraph":
                inner = ADFToMarkdownConverter._render_nodes(
                    node.get("content", []), indent_level
                )
                md += f"{inner.strip()}\n\n"

            elif node_type in ["bulletList", "orderedList"]:
                for i, item in enumerate(node.get("content", []), 1):
                    prefix = f"{i}. " if node_type == "orderedList" else "- "
                    content = ADFToMarkdownConverter._render_nodes(
                        item.get("content", []), indent_level + 1
                    )

                    lines = content.strip().split("\n")
                    if lines:
                        md += f"{'  ' * indent_level}{prefix}{lines[0]}\n"
                        for extra_line in lines[1:]:
                            md += f"{'  ' * (indent_level + 1)}{extra_line}\n"
                md += "\n"

            elif node_type == "listItem":
                md += ADFToMarkdownConverter._render_nodes(
                    node.get("content", []), indent_level
                )

            elif node_type == "text":
                md += ADFToMarkdownConverter._apply_marks(node)

            elif node_type == "hardBreak":
                md += "  \n"

            elif node_type == "rule":
                md += "---\n\n"

        return md

    @staticmethod
    def _apply_marks(node):
        """
        Applies formatting marks to text nodes in a specific order to ensure valid Markdown syntax.
        """
        text = node.get("text", "")
        marks = node.get("marks", [])
        if not marks:
            return text

        priority = {
            "underline": 1,
            "link": 2,
            "code": 3,
            "em": 4,
            "strong": 5,
            "strike": 6,
        }
        sorted_marks = sorted(marks, key=lambda m: priority.get(m["type"], 0))

        for mark in sorted_marks:
            m_type = mark.get("type")
            if m_type == "code":
                text = f"`{text}`"
            elif m_type == "underline":
                text = f"<u>{text}</u>"
            elif m_type == "link":
                href = mark.get("attrs", {}).get("href", "#")
                text = f"[{text}]({href})"
            elif m_type == "em":
                text = f"*{text}*"
            elif m_type == "strong":
                text = f"**{text}**"
            elif m_type == "strike":
                text = f"~~{text}~~"

        return text
