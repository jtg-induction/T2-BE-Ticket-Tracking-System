from rest_framework import serializers

from .jiraclient import JiraClient


class JiraProjectService:
    """
    Service layer for coordinating  jira-related operations with the Jira Cloud API.
    """

    @staticmethod
    def _get_client(user, site_url):
        """
        Helper to instantiate an authenticated JiraClient.

        Args:
            user (CustomUser): The user performing the action.
            site_url (str): The Atlassian site URL.

        Returns:
            JiraClient: An authenticated instance of the Jira client.
        """
        return JiraClient(site_url, user.email, user.get_decrypted_jira_token())

    @staticmethod
    def _get_role_id_by_name(client, project_id, role_name):
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

        return role_url.split("/")[-1]

    @staticmethod
    def create_jira_project(user, project_data):
        """
        Creates a new Software project in Jira Cloud.

        Args:
            user (CustomUser): The user.
            project_data (dict): Data including 'jira_project_key', 'title',
                                 'site_url', and 'description'.

        Returns:
            str: The unique Jira project ID returned by Atlassian on success.
        """
        client = JiraProjectService._get_client(user, project_data["site_url"])

        payload = {
            "key": project_data["jira_project_key"],
            "name": project_data["title"],
            "projectTypeKey": "software",
            "projectTemplateKey": "com.pyxis.greenhopper.jira:gh-simplified-agility-kanban",
            "description": project_data.get("description", ""),
            "leadAccountId": user.jira_id,
            "assigneeType": "PROJECT_LEAD",
        }

        response = client.post("/rest/api/3/project", payload)

        if response.status_code == 201:
            return response.json().get("id")

        raise serializers.ValidationError(
            f"Jira project creation Failed: {response.text}"
        )

    @staticmethod
    def update_jira_project(user, instance, validated_data):
        """
        Updates the project name or description in Jira Cloud.

        Args:
            user (CustomUser): The user performing the update.
            instance (ProjectModel): The existing project model instance.
            validated_data (dict): The dictionary of updated fields.

        Returns:
            None
        """
        client = JiraProjectService._get_client(user, instance.site_url)
        project_id = instance.jira_id

        if "title" in validated_data or "description" in validated_data:
            payload = {
                "name": validated_data.get("title", instance.title),
                "description": validated_data.get("description", instance.description),
            }
            endpoint = f"/rest/api/3/project/{project_id}"
            response = client.put(endpoint, payload)
            if response.status_code not in [200, 204]:
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
