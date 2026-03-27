from rest_framework import serializers

from core import constants as jc
from core.constants import ASSIGNEE_TYPE_LEAD, DEFAULT_PROJECT_TYPE, KANBAN_TEMPLATE
from core.exceptions import (
    JiraAuthenticationError,
    JiraBaseException,
    JiraConnectionError,
    JiraValidationError,
)
from core.jiraclient import JiraClient
from core.utils import ADFConverter


class JiraProjectService:
    """
    Service layer for coordinating jira-related operations with the Jira Cloud API.
    """

    @classmethod
    def _build_url(cls, *parts):
        """
        Internal helper to construct Jira API endpoints.
        Ensures segments are joined with single slashes and prefixed with the versioned API path.
        """
        path = "/".join(str(p).strip("/") for p in parts)
        return f"{jc.JIRA_API_VERSION}/{path}"

    @classmethod
    def _handle_response(cls, response, context_message):
        """
        Internal helper to evaluate Jira responses and raise specific exceptions.
        """
        if response.status_code in jc.HTTP_SUCCESS_CODES:
            return response

        error_detail = response.text

        try:
            data = response.json()
            if data.get("errorMessage"):
                error_detail = data["errorMessage"]
            elif data.get("errors") and isinstance(data["errors"], dict):
                error_detail = ", ".join(
                    [f"{k}: {v}" for k, v in data["errors"].items()]
                )
            elif data.get("message"):
                error_detail = data["message"]
        except (ValueError, AttributeError):
            error_detail = response.text[:200]

        full_msg = f"{context_message}: {error_detail}"

        if response.status_code == jc.HTTP_BAD_REQUEST:
            raise JiraValidationError(full_msg)
        elif response.status_code in [jc.HTTP_UNAUTHORIZED, jc.HTTP_FORBIDDEN]:
            raise JiraAuthenticationError(full_msg)
        elif response.status_code >= jc.HTTP_SERVER_ERROR:
            raise JiraConnectionError(full_msg)

        raise JiraBaseException(full_msg)

    @classmethod
    def _get_client(cls, user, site_url):
        """
        Helper to instantiate an authenticated JiraClient.

        Args:
            user (CustomUser): The user performing the action.
            site_url (str): The Atlassian site URL.

        Returns:
            JiraClient: An authenticated instance of the Jira client.
        """
        try:
            return JiraClient(site_url, user.email, user.get_decrypted_jira_token())
        except Exception as e:
            raise JiraAuthenticationError(f"Failed to initialize Jira Client: {str(e)}")

    @classmethod
    def _get_role_id_by_name(cls, client, project_id, role_name):
        """
        Retrieves the unique numeric ID for a project role by its name.

        Args:
            client (JiraClient): The authenticated Jira client.
            project_id (str): The Jira project ID.
            role_name (str): The name of the role (e.g., 'Administrator').

        Returns:
            str: The numeric ID of the requested role.
        """
        endpoint = cls._build_url("project", project_id, "role")
        response = client.get(endpoint)
        cls._handle_response(response, f"Fetching role '{role_name}'")

        roles = response.json()
        role_url = roles.get(role_name)

        if not role_url:
            raise serializers.ValidationError(
                f"Jira role '{role_name}' not found in project."
            )

        return role_url.split("/")[-1]

    @classmethod
    def create_jira_project(cls, user, project_data):
        """
        Creates a new Software project in Jira Cloud.

        Args:
            user (CustomUser): The user.
            project_data (dict): Data including 'jira_project_key', 'title',
                                 'site_url', and 'description'.

        Returns:
            str: The unique Jira project ID returned by Atlassian on success.
        """
        client = cls._get_client(user, project_data["site_url"])
        payload = {
            "key": project_data["jira_project_key"],
            "name": project_data["title"],
            "projectTypeKey": DEFAULT_PROJECT_TYPE,
            "projectTemplateKey": KANBAN_TEMPLATE,
            "description": project_data.get("description", ""),
            "leadAccountId": user.jira_id,
            "assigneeType": ASSIGNEE_TYPE_LEAD,
        }

        endpoint = cls._build_url("project")
        response = client.post(endpoint, payload)
        cls._handle_response(response, "Jira project creation")
        return response.json().get("id")

    @classmethod
    def update_jira_project(cls, user, instance, validated_data):
        """
        Updates the project name, description, or archive status in Jira Cloud.

        Args:
            user (CustomUser): The user performing the update.
            instance (Project): The existing project model instance.
            validated_data (dict): The dictionary of updated fields.
        """
        client = cls._get_client(user, instance.site_url)
        project_id = instance.jira_id

        if "title" in validated_data or "description" in validated_data:
            payload = {
                "name": validated_data.get("title", instance.title),
                "description": validated_data.get("description", instance.description),
            }
            endpoint = cls._build_url("project", project_id)
            response = client.put(endpoint, payload)
            cls._handle_response(response, "Jira Details Update")

        if "is_archived" in validated_data:
            should_archive = validated_data["is_archived"]
            action = jc.ACTION_ARCHIVE if should_archive else jc.ACTION_RESTORE
            archive_endpoint = cls._build_url("project", project_id, action)
            archive_res = client.post(archive_endpoint, data={})
            cls._handle_response(archive_res, f"Jira Project {action.capitalize()}")

    @classmethod
    def add_user_to_jira_project(cls, user, project, invitee, is_admin) -> bool:
        """
        Synchronizes a project membership with Jira Cloud by assigning the
        invitee to a specific project role.
        """
        client = cls._get_client(user, project.site_url)
        target_role_name = jc.ROLE_ADMINISTRATOR if is_admin else jc.ROLE_MEMBER
        role_id = cls._get_role_id_by_name(client, project.jira_id, target_role_name)

        endpoint = cls._build_url("project", project.jira_id, "role", role_id)
        payload = {"user": [invitee.jira_id]}
        response = client.post(endpoint, payload)
        cls._handle_response(response, f"Adding user to {target_role_name} role")
        return True

    @classmethod
    def update_user_role_in_jira(cls, user, project, target_user, new_role):
        """
        Updates a user's role within a Jira project by cycling their permissions.
        """
        client = cls._get_client(user, project.site_url)

        admin_role_id = cls._get_role_id_by_name(
            client, project.jira_id, jc.ROLE_ADMINISTRATOR
        )
        member_role_id = cls._get_role_id_by_name(
            client, project.jira_id, jc.ROLE_MEMBER
        )

        for role_id in [admin_role_id, member_role_id]:
            endpoint = cls._build_url("project", project.jira_id, "role", role_id)
            params = {"user": target_user.jira_id}
            response = client.delete(endpoint, params=params)

            if response.status_code != jc.HTTP_NOT_FOUND:
                cls._handle_response(response, "Clearing old Jira role")

        is_admin = new_role in ["admin", "owner"]
        return cls.add_user_to_jira_project(user, project, target_user, is_admin)

    @classmethod
    def remove_user_from_jira_project(cls, user, project, target_user):
        """
        Removes a user from all recognized roles in a Jira project.
        """
        client = cls._get_client(user, project.site_url)

        admin_role_id = cls._get_role_id_by_name(
            client, project.jira_id, jc.ROLE_ADMINISTRATOR
        )
        member_role_id = cls._get_role_id_by_name(
            client, project.jira_id, jc.ROLE_MEMBER
        )

        for role_id in [admin_role_id, member_role_id]:
            endpoint = cls._build_url("project", project.jira_id, "role", role_id)
            params = {"user": target_user.jira_id}
            response = client.delete(endpoint, params=params)

            if response.status_code != jc.HTTP_NOT_FOUND:
                cls._handle_response(response, f"Jira Removal (Role: {role_id})")

        return True

    @classmethod
    def create_jira_task(
        cls,
        user,
        project_instance,
        summary,
        description,
        reporter_id,
        category,
        priority="Medium",
        due_date=None,
        status_name=None,
    ):
        """
        Creates a new issue in Jira Cloud and optionally transitions its status.
        """
        client = cls._get_client(user, project_instance.site_url)
        description_adf = {
            "version": jc.ADF_VERSION,
            "type": jc.ADF_TYPE_DOC,
            "content": [
                {
                    "type": jc.ADF_TYPE_PARAGRAPH,
                    "content": [{"type": jc.ADF_TYPE_TEXT, "text": description}],
                }
            ],
        }
        payload = {
            "fields": {
                "project": {"id": project_instance.jira_id},
                "summary": summary,
                "description": description_adf,
                "issuetype": {"name": jc.ISSUE_TYPE_TASK},
                "reporter": {"id": reporter_id},
                "priority": {"name": priority},
                "labels": [category],
            }
        }

        if due_date:
            payload["fields"]["duedate"] = due_date

        endpoint = cls._build_url("issue")
        response = client.post(endpoint, payload)
        cls._handle_response(response, "Jira Task Creation")
        jira_data = response.json()
        jira_key = jira_data.get("key")

        if status_name and status_name.lower() != jc.STATUS_TO_DO:
            search_status = (
                jc.STATUS_DONE
                if status_name.lower() == jc.STATUS_CLOSED
                else status_name.lower()
            )

            transitions = cls._get_available_transitions(client, jira_key)
            transition_id = next(
                (
                    t["id"]
                    for t in transitions
                    if t["to"]["name"].lower() == search_status
                ),
                None,
            )

            if transition_id:
                transition_payload = {"transition": {"id": transition_id}}
                trans_endpoint = cls._build_url("issue", jira_key, "transitions")
                trans_res = client.post(trans_endpoint, transition_payload)
                cls._handle_response(
                    trans_res, f"Initial Status Transition to '{status_name}'"
                )

        return jira_data

    @classmethod
    def _get_available_transitions(cls, client, jira_id):
        """
        Retrieves the valid workflow transitions for a specific Jira issue.
        """
        endpoint = cls._build_url("issue", jira_id, "transitions")
        response = client.get(endpoint)
        cls._handle_response(response, f"Fetching transitions for {jira_id}")
        return response.json().get("transitions", [])

    @classmethod
    def update_jira_task(cls, user, ticket_instance, validated_data):
        """
        Synchronizes local ticket updates to the external Jira issue.
        """
        client = cls._get_client(user, ticket_instance.project.site_url)
        jira_id = ticket_instance.jira_id

        new_status = validated_data.get("status")
        if new_status and new_status != ticket_instance.status:
            search_status = (
                jc.STATUS_DONE
                if new_status.lower() == jc.STATUS_CLOSED
                else new_status.lower()
            )
            transitions = cls._get_available_transitions(client, jira_id)
            transition_id = next(
                (
                    t["id"]
                    for t in transitions
                    if t["to"]["name"].lower() == search_status
                ),
                None,
            )

            if transition_id:
                transition_payload = {"transition": {"id": transition_id}}
                trans_endpoint = cls._build_url("issue", jira_id, "transitions")
                cls._handle_response(
                    client.post(trans_endpoint, transition_payload), "Status Update"
                )
            else:
                allowed = [t["to"]["name"] for t in transitions]
                raise serializers.ValidationError(
                    f"Invalid transition. Options: {', '.join(allowed)}"
                )

        fields = {}
        if "deadline" in validated_data:
            deadline = validated_data.get("deadline")
            fields["duedate"] = deadline.strftime("%Y-%m-%d") if deadline else None

        if "name" in validated_data:
            fields["summary"] = validated_data["name"]

        if "description" in validated_data:
            fields["description"] = {
                "version": jc.ADF_VERSION,
                "type": jc.ADF_TYPE_DOC,
                "content": [
                    {
                        "type": jc.ADF_TYPE_PARAGRAPH,
                        "content": [
                            {
                                "type": jc.ADF_TYPE_TEXT,
                                "text": validated_data["description"],
                            }
                        ],
                    }
                ],
            }

        if "priority" in validated_data:
            fields["priority"] = {"name": validated_data["priority"]}

        if "category" in validated_data:
            fields["labels"] = [validated_data["category"]]

        if "assignee" in validated_data:
            assignee_obj = validated_data.get("assignee")
            fields["assignee"] = {"id": assignee_obj.jira_id} if assignee_obj else None

        if fields:
            endpoint = cls._build_url("issue", jira_id)
            cls._handle_response(
                client.put(endpoint, {"fields": fields}), "Field Update"
            )

        return True

    @classmethod
    def search_jira_tickets(
        cls, user, project_instance, jql_query, maxResults, nextPageToken=None
    ):
        """
        Performs a scoped JQL search against the Jira project.
        """
        client = cls._get_client(user, project_instance.site_url)
        scoped_jql = (
            f"project = '{project_instance.jira_project_key}' AND ({jql_query})"
        )

        payload = {
            "jql": scoped_jql,
            "fields": [
                "summary",
                "status",
                "assignee",
                "reporter",
                "priority",
                "description",
                "labels",
            ],
            "maxResults": maxResults or jc.DEFAULT_MAX_RESULTS,
            "nextPageToken": nextPageToken,
        }

        endpoint = cls._build_url("search", "jql")
        response = client.post(endpoint, payload)
        cls._handle_response(response, "Jira JQL Search")

        data = response.json()
        return {
            "issues": data.get("issues", []),
            "next_page_token": data.get("nextPageToken"),
            "total": data.get("total", 0),
        }

    @classmethod
    def add_comment_to_jira(cls, user, ticket_instance, message):
        """Adds a new comment to a Jira issue."""
        client = cls._get_client(user, ticket_instance.project.site_url)
        payload = {"body": ADFConverter.to_adf(message)}
        endpoint = cls._build_url("issue", ticket_instance.jira_id, "comment")
        response = client.post(endpoint, payload)
        cls._handle_response(response, "Adding Jira Comment")
        return response.json().get("id")

    @classmethod
    def update_jira_comment(
        cls, user, ticket_instance, jira_comment_id, message
    ) -> bool:
        """Updates an existing Jira comment."""
        client = cls._get_client(user, ticket_instance.project.site_url)
        payload = {"body": ADFConverter.to_adf(message)}
        endpoint = cls._build_url(
            "issue", ticket_instance.jira_id, "comment", jira_comment_id
        )
        cls._handle_response(client.put(endpoint, payload), "Updating Jira Comment")
        return True

    @classmethod
    def delete_jira_comment(cls, user, ticket_instance, jira_comment_id) -> bool:
        """Deletes a specific Jira comment."""
        client = cls._get_client(user, ticket_instance.project.site_url)
        endpoint = cls._build_url(
            "issue", ticket_instance.jira_id, "comment", jira_comment_id
        )
        cls._handle_response(client.delete(endpoint), "Deleting Jira Comment")
        return True

    @classmethod
    def fetch_jira_comments(cls, user, project_instance, ticket_jira_id) -> list:
        """Fetches all comments for a specific Jira issue."""
        client = cls._get_client(user, project_instance.site_url)
        endpoint = cls._build_url("issue", ticket_jira_id, "comment")
        response = client.get(endpoint)
        cls._handle_response(response, "Fetching Jira Comments")
        return response.json().get("comments", [])
