import re
from urllib.parse import urlparse

from django.db import transaction
from rest_framework import serializers

from core.services import JiraProjectService

from .enums import MemberStatus
from .models import ProjectMember, ProjectModel


class ProjectSerializer(serializers.ModelSerializer):
    """
    Serializer to handle Project data with Jira integration logic.

    Responsible for validating Atlassian-specific fields (Project Key, Site URL),and coordinating with
    JiraProjectService to keep external Jira projects in sync with the database.
    """

    owner_email = serializers.EmailField(source="owner.email", read_only=True)

    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = ProjectModel
        fields = [
            "id",
            "title",
            "description",
            "jira_id",
            "jira_project_key",
            "site_url",
            "is_archived",
            "owner_email",
            "can_edit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "jira_id",
            "owner_email",
            "can_edit",
            "created_at",
            "updated_at",
        ]

    def get_can_edit(self, obj):
        """
        Computes whether the current requester has administrative rights to the project.

        Returns:
            bool: True if the user has edit permissions, False otherwise.
        """
        request = self.context.get("request")

        if request.user.is_staff or obj.owner == request.user:
            return True
        return ProjectMember.objects.filter(
            project=obj, user=request.user, is_admin=True, status=MemberStatus.MEMBER
        ).exists()

    def validate_jira_project_key(self, value):
        """
        Validates that the Jira Project Key meets Atlassian's standard requirements.

        Regex Pattern: ^[A-Z][A-Z0-9]{1,9}$
        Requirements: Must be uppercase, start with a letter, and be 2-10 characters long.
        """
        pattern = r"^[A-Z][A-Z0-9]{1,9}$"
        if not re.match(pattern, value):
            raise serializers.ValidationError(
                "Jira Project Key must be uppercase, start with a letter, and must be 2-10 chars in length."
            )
        return value

    def validate_site_url(self, value):
        """
        Ensures the site URL is a secured, valid Atlassian Cloud domain.
        """
        value = value.strip().rstrip("/")

        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()

        if parsed.scheme != "https":
            raise serializers.ValidationError("Site URL must use HTTPS for security.")

        if not host.endswith(".atlassian.net"):
            raise serializers.ValidationError(
                "Site URL must be a valid Atlassian Cloud domain (e.g., company.atlassian.net)."
            )

        return f"https://{host}"

    def validate(self, attrs):
        """
        Performs cross-field validation and prevents modification of immutable fields.
        """
        if self.instance:
            if "site_url" in attrs and attrs["site_url"] != self.instance.site_url:
                raise serializers.ValidationError(
                    {
                        "site_url": "You cannot change the Site URL once a project is linked."
                    }
                )
            if (
                "jira_project_key" in attrs
                and attrs["jira_project_key"] != self.instance.jira_project_key
            ):
                raise serializers.ValidationError(
                    {
                        "jira_project_key": "You cannot change the Project Key after creation."
                    }
                )

        else:
            key = attrs.get("jira_project_key")
            url = attrs.get("site_url")
            if ProjectModel.all_objects.filter(
                jira_project_key=key, site_url=url
            ).exists():
                raise serializers.ValidationError(
                    "This project key already exists for this site URL."
                )

        return attrs

    def create(self, validated_data):
        """
        Creates a local ProjectModel instance and its remote Jira counterpart.
        """
        user = self.context["request"].user
        with transaction.atomic():
            project = ProjectModel.objects.create_with_user(user=user, **validated_data)
            jira_id = JiraProjectService.create_jira_project(user, validated_data)
            project.jira_id = jira_id
            project.save()
            return project

    def update(self, instance, validated_data):
        """
        Updates the local project and triggers a remote update in Jira.
        """
        user = self.context["request"].user
        with transaction.atomic():
            validated_data["updated_by"] = user
            instance = super().update(instance, validated_data)
            JiraProjectService.update_jira_project(user, instance, validated_data)
            return instance
