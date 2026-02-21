from rest_framework import serializers

from .constants import ASSIGNEE_TYPE_LEAD, DEFAULT_PROJECT_TYPE, KANBAN_TEMPLATE
from .jiraclient import JiraClient


class JiraProjectService:
    """
    Service layer for coordinating  jira-related operations with the Jira Cloud API.
    """

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
        return JiraClient(site_url, user.email, user.get_decrypted_jira_token())

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

        if response.status_code != 200:
            raise serializers.ValidationError(
                f"Could not fetch Jira roles: {response.text}"
            )

        roles = response.json()
        role_url = roles.get(role_name)

        if not role_url:
            raise serializers.ValidationError(f"Jira role '{role_name}' not found.")
        try:
            return role_url.split("/")[-1]
        except (AttributeError, IndexError, ValueError):
            raise serializers.ValidationError(
                f"Jira returned an invalid URL format for role '{role_name}'."
            )

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

        if response.status_code == 201:
            return response.json().get("id")

        raise serializers.ValidationError(
            f"Jira project creation Failed: {response.text}"
        )

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
            if response.status_code not in (200, 204):
                raise serializers.ValidationError(
                    f"Jira Details Update Failed: {response.text}"
                )

        if "is_archived" in validated_data:
            should_archive = validated_data["is_archived"]
            action = "archive" if should_archive else "restore"
            archive_endpoint = f"/rest/api/3/project/{project_id}/{action}"

            archive_res = client.post(archive_endpoint, data={})

            if archive_res.status_code not in [200, 204]:
                if archive_res.status_code != 403:
                    raise serializers.ValidationError(
                        f"Jira {action} Failed: {archive_res.text}"
                    )

    @classmethod
    def add_user_to_jira_project(cls, user, project, invitee, is_admin):
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

        if response.status_code not in [200, 201]:
            raise serializers.ValidationError(
                f"Failed to add user to Jira: {response.text}"
            )

        return True
