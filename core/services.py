from rest_framework import serializers

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
    Service layer for coordinating  jira-related operations with the Jira Cloud API.
    """

    @classmethod
    def _handle_response(cls, response, context_message):
        """
        Internal helper to evaluate Jira responses and raise specific exceptions.
        """
        if response.status_code in [200, 201, 204]:
            return response

        error_detail = response.text

        try:
            data = response.json()
            if data.get("errorMessages"):
                error_detail = " ".join(data["errorMessages"])
            elif data.get("errors") and isinstance(data["errors"], dict):
                error_detail = ", ".join(
                    [f"{k}: {v}" for k, v in data["errors"].items()]
                )
            elif data.get("message"):
                error_detail = data["message"]
        except (ValueError, AttributeError):
            error_detail = response.text[:200]

        full_msg = f"{context_message}: {error_detail}"

        if response.status_code == 400:
            raise JiraValidationError(full_msg)
        elif response.status_code in [401, 403]:
            raise JiraAuthenticationError(full_msg)
        elif response.status_code >= 500:
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
        Retrieves the unique numeric ID for a project role by its name.'

        Args:
            client (JiraClient): The authenticated Jira client.
            project_id (str): The Jira project ID.
            role_name (str): The name of the role.

        Returns:
            str: The numeric ID of the requested role.
        """

        response = client.get(f"/rest/api/3/project/{project_id}/role")
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

        response = client.post("/rest/api/3/project", payload)
        cls._handle_response(response, "Jira project creation")
        return response.json().get("id")

    @classmethod
    def update_jira_project(cls, user, instance, validated_data):
        """
        Updates the project name or description in Jira Cloud.

        Args:
            user (CustomUser): The user performing the update.
            instance (ProjectModel): The existing project model instance.
            validated_data (dict): The dictionary of updated fields.

        Returns:
            None
        """
        client = cls._get_client(user, instance.site_url)
        project_id = instance.jira_id

        if "title" in validated_data or "description" in validated_data:
            payload = {
                "name": validated_data.get("title", instance.title),
                "description": validated_data.get("description", instance.description),
            }
            endpoint = f"/rest/api/3/project/{project_id}"
            response = client.put(endpoint, payload)
            cls._handle_response(response, "Jira Details Update")

        if "is_archived" in validated_data:
            should_archive = validated_data["is_archived"]
            action = "archive" if should_archive else "restore"
            archive_endpoint = f"/rest/api/3/project/{project_id}/{action}"
            archive_res = client.post(archive_endpoint, data={})
            cls._handle_response(archive_res, f"Jira Project {action.capitalize()}")

    @classmethod
    def add_user_to_jira_project(cls, user, project, invitee, is_admin) -> bool:
        """
        Synchronizes a project membership with Jira Cloud by assigning the
        invitee to a specific project role.

        Args:
            user (CustomUser): The user performing the action.
            project (ProjectModel): The project instance being modified.
            invitee (CustomUser): The user being added to the project.
            is_admin (bool): Flag determining the level of access to grant in Jira.

        Returns:
            bool: True if the user was successfully added to the Jira role.

        """

        client = cls._get_client(user, project.site_url)
        target_role_name = "Administrator" if is_admin else "Member"
        role_id = cls._get_role_id_by_name(client, project.jira_id, target_role_name)
        endpoint = f"/rest/api/3/project/{project.jira_id}/role/{role_id}"
        payload = {"user": [invitee.jira_id]}
        response = client.post(endpoint, payload)
        cls._handle_response(response, f"Adding user to {target_role_name} role")
        return True

    @classmethod
    def update_user_role_in_jira(cls, user, project, target_user, new_role):
        """
        Updates a user's role within a Jira project by cycling their permissions.

        Args:
            user (User): The requester performing the update.
            project (ProjectModel): The local project instance containing Jira data.
            target_user (User): The user whose permissions are being changed.
            new_role (str): The desired role.

        Returns:
            bool: True if the user was successfully added to the new role.
        """
        client = cls._get_client(user, project.site_url)

        admin_role_id = cls._get_role_id_by_name(
            client, project.jira_id, "Administrator"
        )
        member_role_id = cls._get_role_id_by_name(client, project.jira_id, "Member")

        for role_id in [admin_role_id, member_role_id]:
            endpoint = f"/rest/api/3/project/{project.jira_id}/role/{role_id}"
            params = {"user": target_user.jira_id}
            response = client.delete(endpoint, params=params)

            if response.status_code != 404:
                cls._handle_response(response, "Clearing old Jira role")

        is_admin = new_role in ["admin", "owner"]
        return cls.add_user_to_jira_project(user, project, target_user, is_admin)

    @classmethod
    def remove_user_from_jira_project(cls, user, project, target_user):
        """
        Removes a user from all recognized roles in a Jira project.

        Args:
            user (User): The requester performing the removal.
            project (ProjectModel): The project from which the user is being removed.
            target_user (User): The user being removed.

        Returns:
            bool: True if all removal requests were successful or the user
                  already had no roles.
        """
        client = cls._get_client(user, project.site_url)

        admin_role_id = cls._get_role_id_by_name(
            client, project.jira_id, "Administrator"
        )
        member_role_id = cls._get_role_id_by_name(client, project.jira_id, "Member")

        for role_id in [admin_role_id, member_role_id]:
            endpoint = f"/rest/api/3/project/{project.jira_id}/role/{role_id}"
            params = {"user": target_user.jira_id}
            response = client.delete(endpoint, params=params)

            if response.status_code != 404:
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
        Creates a new issue in Jira Cloud.

        Args:
            user (User): The local user performing the action (used for authentication).
            project_instance (ProjectModel): The project where the task will be created.
            summary (str): The title of the Jira issue.
            description (str): Plain text description (converted to ADF paragraph).
            reporter_id (str): The Jira Account ID of the reporter.
            category (str): Local category used as a Jira label.
            priority (str): Jira priority name (default: "Medium").
            due_date (str|None): Optional ISO date string (YYYY-MM-DD).

        Returns:
            dict: The JSON response from Jira containing the new issue key and ID.

        """
        client = cls._get_client(user, project_instance.site_url)
        description_adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                }
            ],
        }
        payload = {
            "fields": {
                "project": {"id": project_instance.jira_id},
                "summary": summary,
                "description": description_adf,
                "issuetype": {"name": "Task"},
                "reporter": {"id": reporter_id},
                "priority": {"name": priority},
                "labels": [category],
            }
        }

        if due_date:
            payload["fields"]["duedate"] = due_date

        response = client.post("/rest/api/3/issue", payload)
        cls._handle_response(response, "Jira Task Creation")
        jira_data = response.json()
        jira_id = jira_data.get("key")

        if status_name and status_name.lower() != "to do":
            search_status = (
                "done" if status_name.lower() == "closed" else status_name.lower()
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
                trans_res = client.post(
                    f"/rest/api/3/issue/{jira_id}/transitions", transition_payload
                )
                cls._handle_response(
                    trans_res, f"Initial Jira Status Transition to '{status_name}'"
                )

        return jira_data

    @classmethod
    def _get_available_transitions(cls, client, jira_id):
        """
        Retrieves the valid workflow transitions for a specific Jira issue.

        In Jira, status changes are not direct edits; you must move an issue
        through defined 'transitions' allowed by the project's workflow.

        Args:
            client (JiraClient): The authenticated Jira API client.
            jira_id (str): The Jira issue key.

        Returns:
            list: A list of transition dictionaries containing IDs and 'to' names.
        """
        endpoint = f"/rest/api/3/issue/{jira_id}/transitions"
        response = client.get(endpoint)
        cls._handle_response(response, f"Fetching transitions for {jira_id}")

        return response.json().get("transitions", [])

    @classmethod
    def update_jira_task(cls, user, ticket_instance, validated_data):
        """
        Synchronizes local ticket updates to the external Jira issue.

        Handles two distinct Jira operations:
        1. **Workflow Transitions**: If the status changes, it fetches available
           transitions and executes the correct ID to move the issue.
        2. **Field Updates**: Updates summary, description, priority, labels,
           and assignee via a PUT request.

        Args:
            user (User): The local user performing the update.
            ticket_instance (Ticket): The local ticket being modified.
            validated_data (dict): Cleaned data from the serializer.

        Returns:
            bool: True if synchronization was successful.
        """
        client = cls._get_client(user, ticket_instance.project.site_url)
        jira_id = ticket_instance.jira_id

        new_status = validated_data.get("status")
        if new_status and new_status != ticket_instance.status:
            search_status = (
                "done" if new_status.lower() == "closed" else new_status.lower()
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
                trans_response = client.post(
                    f"/rest/api/3/issue/{jira_id}/transitions", transition_payload
                )

                cls._handle_response(
                    trans_response, f"Jira Status Transition to '{search_status}'"
                )
            else:
                allowed_statuses = [t["to"]["name"] for t in transitions]
                raise serializers.ValidationError(
                    f"Jira status '{search_status}' is not a valid move from current state. "
                    f"Available options: {', '.join(allowed_statuses)}"
                )

        fields = {}

        if "deadline" in validated_data:
            deadline = validated_data.get("deadline")
            fields["duedate"] = deadline.strftime("%Y-%m-%d") if deadline else None

        if "name" in validated_data:
            fields["summary"] = validated_data["name"]

        if "description" in validated_data:
            fields["description"] = {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": validated_data["description"]}
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
            if assignee_obj:
                fields["assignee"] = {"id": assignee_obj.jira_id}
            else:
                fields["assignee"] = None

        if fields:
            endpoint = f"/rest/api/3/issue/{jira_id}"
            response = client.put(endpoint, {"fields": fields})

            cls._handle_response(response, "Jira Task Field Update")

        return True

    @classmethod
    def search_jira_tickets(
        cls, user, project_instance, jql_query, maxResults, nextPageToken=None
    ):
        """
        Performs a scoped JQL search against the Jira project.

        Combines the user's search query with a project-level scope to ensure
        results are limited to the relevant Jira project. Supports modern
        token-based pagination.

        Args:
            user (User): The local user performing the search.
            project_instance (ProjectModel): The project to scope the search to.
            jql_query (str): The raw JQL string (e.g., 'text ~ "login"').
            maxResults (int): Number of results to return per page.
            nextPageToken (str|None): The token for the next page of results.

        Returns:
            dict: A dictionary containing 'issues' (list), 'next_page_token' (str),
                  and 'total' (int).
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
            "maxResults": maxResults,
            "nextPageToken": nextPageToken,
        }

        response = client.post("/rest/api/3/search/jql", payload)

        cls._handle_response(response, "Jira JQL Search")

        data = response.json()
        return {
            "issues": data.get("issues", []),
            "next_page_token": data.get("nextPageToken"),
            "total": data.get("total", 0),
        }

    @classmethod
    def add_comment_to_jira(cls, user, ticket_instance, message):
        client = cls._get_client(user, ticket_instance.project.site_url)
        payload = {"body": ADFConverter.to_adf(message)}
        endpoint = f"/rest/api/3/issue/{ticket_instance.jira_id}/comment"
        response = client.post(endpoint, payload)

        cls._handle_response(response, "Adding Jira Comment")
        return response.json().get("id")

    @classmethod
    def update_jira_comment(
        cls, user, ticket_instance, jira_comment_id, message
    ) -> bool:
        client = cls._get_client(user, ticket_instance.project.site_url)
        payload = {"body": ADFConverter.to_adf(message)}
        endpoint = (
            f"/rest/api/3/issue/{ticket_instance.jira_id}/comment/{jira_comment_id}"
        )
        response = client.put(endpoint, payload)
        cls._handle_response(response, "Updating Jira Comment")
        return True

    @classmethod
    def delete_jira_comment(cls, user, ticket_instance, jira_comment_id) -> bool:
        client = cls._get_client(user, ticket_instance.project.site_url)
        endpoint = (
            f"/rest/api/3/issue/{ticket_instance.jira_id}/comment/{jira_comment_id}"
        )
        response = client.delete(endpoint)
        cls._handle_response(response, "Deleting Jira Comment")
        return True

    @classmethod
    def fetch_jira_comments(cls, user, project_instance, ticket_jira_id) -> list:
        client = cls._get_client(user, project_instance.site_url)
        endpoint = f"/rest/api/3/issue/{ticket_jira_id}/comment"
        response = client.get(endpoint)

        cls._handle_response(response, "Fetching Jira Comments")
        return response.json().get("comments", [])
