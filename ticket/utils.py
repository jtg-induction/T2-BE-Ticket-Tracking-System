from ticket.models import Ticket


def parse_jira_adf(adf_data):
    """Extract text from ADF."""
    if not adf_data or not isinstance(adf_data, dict):
        return str(adf_data) if adf_data else ""

    extracted_text = []
    for node in adf_data.get("content", []):
        if "text" in node:
            extracted_text.append(node["text"])
        elif "content" in node:
            extracted_text.append(parse_jira_adf(node))

    return " ".join(extracted_text).strip()


def map_jira_to_ticket(issue, project_instance):
    """Map Jira JSON to model."""
    fields = issue.get("fields", {})
    raw_description = fields.get("description") or ""

    description = (
        parse_jira_adf(raw_description)
        if isinstance(raw_description, dict)
        else raw_description
    )
    ticket = Ticket(
        jira_id=issue.get("key"),
        name=fields.get("summary", ""),
        description=description,
        project=project_instance,
        status=fields.get("status", {}).get("name", "To Do"),
        priority=fields.get("priority", {}).get("name", "Medium"),
    )

    ticket._jira_assignee_id = (fields.get("assignee") or {}).get("accountId")
    ticket._jira_reporter_id = (fields.get("reporter") or {}).get("accountId")

    return ticket
