import re
from urllib.parse import urlparse

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from core.services.jira import JiraProjectService
from project.constants import ProjectMessages
from project.enums import MemberStatus, ProjectRole
from project.models import ProjectInvitation, ProjectMember, ProjectModel
from project.services import ProjectService
from user.models import CustomUser
from user.serializers import UserSerializer


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

        if obj.owner == request.user:
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
            raise serializers.ValidationError(ProjectMessages.KEY_REQUIREMENTS)
        return value

    def validate_site_url(self, value):
        """
        Ensures the site URL is a secured, valid Atlassian Cloud domain.
        """
        value = value.strip().rstrip("/")

        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()

        if parsed.scheme != "https":
            raise serializers.ValidationError(ProjectMessages.HTTPS_REQUIRED)

        if not host.endswith(".atlassian.net"):
            raise serializers.ValidationError(ProjectMessages.ATL_DOMAIN_REQUIRED)

        return f"https://{host}"

    def validate(self, attrs):
        """
        Performs cross-field validation and prevents modification of immutable fields.
        """
        if self.instance:
            if "site_url" in attrs and attrs["site_url"] != self.instance.site_url:
                raise serializers.ValidationError(
                    {"site_url": ProjectMessages.IMMUTABLE_SITE}
                )
            if (
                "jira_project_key" in attrs
                and attrs["jira_project_key"] != self.instance.jira_project_key
            ):
                raise serializers.ValidationError(
                    {"jira_project_key": ProjectMessages.IMMUTABLE_KEY}
                )

        else:
            key = attrs.get("jira_project_key")
            url = attrs.get("site_url")
            if ProjectModel.all_objects.filter(
                jira_project_key=key, site_url=url
            ).exists():
                raise serializers.ValidationError(ProjectMessages.DUPLICATE_PROJECT)

        return attrs

    def create(self, validated_data):
        """
        Creates a local ProjectModel instance and its remote Jira counterpart.
        """
        user = self.context["request"].user

        jira_id = JiraProjectService.create_jira_project(user, validated_data)

        with transaction.atomic():
            validated_data["jira_id"] = jira_id
            project = ProjectModel.objects.create_with_user(user=user, **validated_data)
            return project

    def update(self, instance, validated_data):
        """
        Updates the local project and triggers a remote update in Jira.
        """
        user = self.context["request"].user
        validated_data["updated_by"] = user

        JiraProjectService.update_jira_project(user, instance, validated_data)

        return super().update(instance, validated_data)


class InviteUserSerializer(serializers.Serializer):
    """
    Serializer to handle inviting a new user.
    Restores the logic to clear expired invitations before re-inviting.
    """

    user_id = serializers.UUIDField()
    is_admin = serializers.BooleanField(default=False)

    def validate(self, attrs):
        project_id = self.context.get("project_id")

        try:
            invitee = CustomUser.objects.get(user_id=attrs["user_id"])
            attrs["invitee"] = invitee
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError(ProjectMessages.USER_NOT_FOUND)

        if ProjectMember.objects.filter(
            project_id=project_id, user=invitee, status=MemberStatus.MEMBER
        ).exists():
            raise serializers.ValidationError(ProjectMessages.ALREADY_MEMBER)

        ProjectInvitation.objects.filter(
            project_id=project_id, invitee=invitee, expires_at__lte=timezone.now()
        ).delete()

        return attrs

    def create(self, validated_data):
        """
        Delegates to service layer for the actual creation and email dispatch.
        """
        project = get_object_or_404(ProjectModel, id=self.context.get("project_id"))
        return ProjectService.create_invitation(
            project=project,
            invited_by=self.context.get("request").user,
            invitee=validated_data["invitee"],
            is_admin=validated_data["is_admin"],
        )


class ProjectMemberSerializer(serializers.ModelSerializer):
    """
    Serializer for the ProjectMember model.
    """

    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    projectRole = serializers.SerializerMethodField()

    class Meta:
        model = ProjectMember
        fields = [
            "first_name",
            "last_name",
            "user_id",
            "email",
            "full_name",
            "projectRole",
            "is_admin",
            "created_at",
        ]

    def get_projectRole(self, obj):
        """
        Determines the member's role priority.

        Returns:
            str: 'owner' if the user matches the project owner ID,
                 'admin' if the is_admin flag is True,
                 otherwise 'member'.
        """
        if obj.project.owner_id == obj.user_id:
            return ProjectRole.OWNER
        return ProjectRole.ADMIN if obj.is_admin else ProjectRole.MEMBER


class ProjectUserMembershipSerializer(UserSerializer):
    """
    Extends the base UserSerializer to include project membership status.
    """

    is_project_member = serializers.BooleanField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["is_project_member"]
