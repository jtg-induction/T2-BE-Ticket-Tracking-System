from celery import shared_task
from django.contrib.auth import get_user_model

from comment.models import CommentModel
from core.services import JiraProjectService
from core.utils import ADFToMarkdownConverter
from project.models import ProjectModel
from ticket.models import Ticket

User = get_user_model()


@shared_task
def sync_comments_in_batches(ticket_id, user_id, project_id):
    """
    Asynchronously synchronizes comments from a Jira issue to the local database.

    This task performs a paginated fetch from Jira's REST API, converts Jira's
    ADF (Atlassian Document Format) to Markdown, and performs a bulk creation
    of local CommentModel instances.

    Args:
        ticket_id (uuid): The ID of the local Ticket instance.
        user_id (uuid): The ID of the User whose Jira credentials will be used.
        project_id (uuid): The ID of the Project containing the Jira site configuration.

    Logic:
        1. Iterates through Jira comments using `startAt` and `maxResults` pagination.
        2. Maps Jira `accountId` to local `User` objects to maintain attribution.
        3. If a Jira author doesn't exist locally, stores their name in `external_author_name`.
    """
    ticket = Ticket.objects.get(id=ticket_id)
    project = ProjectModel.objects.get(id=project_id)
    user = User.objects.get(user_id=user_id)
    client = JiraProjectService._get_client(user, project.site_url)

    start_at = 0
    max_results = 100

    while True:
        endpoint = f"/rest/api/3/issue/{ticket.jira_id}/comment?startAt={start_at}&maxResults={max_results}"
        response = client.get(endpoint)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to sync Jira comments for ticket {ticket_id} "
                f"at startAt={start_at}: status={response.status_code}"
            )

        data = response.json()
        jira_comments = data.get("comments", [])
        if not jira_comments:
            break

        comment_objs = []
        author_ids = {
            c.get("author", {}).get("accountId")
            for c in jira_comments
            if c.get("author")
        }
        user_map = {u.jira_id: u for u in User.objects.filter(jira_id__in=author_ids)}

        for comment_data in jira_comments:
            md_message = ADFToMarkdownConverter.to_markdown(comment_data.get("body"))

            if not md_message.strip():
                continue

            j_author_id = comment_data.get("author", {}).get("accountId")
            j_display_name = comment_data.get("author", {}).get("displayName")
            local_author = user_map.get(j_author_id)

            comment_objs.append(
                CommentModel(
                    jira_id=comment_data.get("id"),
                    message=md_message,
                    ticket=ticket,
                    commentator=local_author,
                    external_author_name=None if local_author else j_display_name,
                )
            )

        if comment_objs:
            CommentModel.objects.bulk_create(comment_objs, ignore_conflicts=True)

        total_available = data.get("total", 0)
        start_at += len(jira_comments)

        if start_at >= total_available:
            break
