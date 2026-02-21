import re
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from core.services import JiraProjectService
from core.utils import parse_jira_error
from project.models import ProjectMember
from user.models import CustomUser

from .enums import MemberStatus
from .models import ProjectInvitation, ProjectModel
from .tasks import send_invitation_email


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

        try:
            jira_id = JiraProjectService.create_jira_project(user, validated_data)
        except Exception as e:
            clean_error = parse_jira_error(e)
            raise serializers.ValidationError({"detail": clean_error})

        with transaction.atomic():
            validated_data["jira_id"] = jira_id
            validated_data["owner_id"] = user.user_id
            return super().create(validated_data)

    def update(self, instance, validated_data):
        """
        Updates the local project and triggers a remote update in Jira.
        """
        user = self.context["request"].user
        validated_data["updated_by"] = user

        try:
            JiraProjectService.update_jira_project(user, instance, validated_data)
        except Exception as e:
            clean_error = parse_jira_error(e)
            raise serializers.ValidationError({"detial": clean_error})

        return super().update(instance, validated_data)


class InviteUserSerializer(serializers.Serializer):
    """
    Serializer to handle inviting a new user to a project.

    """

    email = serializers.EmailField()
    is_admin = serializers.BooleanField(default=False)

    def validate(self, attrs):
        """
        Performs multi-layered validation for the invitation request.

        1. Verifies the invitee is a registered system user.
        2. Ensures the user isn't already a member of the project.
        3. Checks for existing active (unexpired and unaccepted) invitations
           to prevent spamming.

        Args:
            attrs (dict): Data provided by the requester.

        Returns:
            dict: Validated data with the 'invitee' object injected.
        """
        project_id = self.context.get("project_id")
        email = attrs.get("email")

        try:
            invitee = CustomUser.objects.get(email=email)
            attrs["invitee"] = invitee
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError(
                {"email": "User with this email does not exist."}
            ) from None

        if ProjectMember.objects.filter(project_id=project_id, user=invitee).exists():
            raise serializers.ValidationError(
                "User is already a member of this project."
            )

        ProjectInvitation.objects.filter(
            project_id=project_id,
            invitee=invitee,
            is_accepted=False,
            expires_at__lte=timezone.now(),
        ).delete()

        return attrs

    def create(self, validated_data):
        """
        Creates a ProjectInvitation record and dispatches an invitation email.

        Args:
            validated_data (dict): Data returned from the validation step.

        Returns:
            ProjectInvitation: The newly created invitation instance.
        """
        project_id = self.context.get("project_id")
        inviter = self.context.get("request").user
        invitee = validated_data["invitee"]

        with transaction.atomic():
            invitation = ProjectInvitation.objects.create(
                project_id=project_id,
                invitee=invitee,
                invited_by=inviter,
                is_admin=validated_data["is_admin"],
            )

            invite_url = f"{settings.CLIENT_URL}/accept-invite/{invitation.token}"

            try:
                transaction.on_commit(
                    lambda: send_invitation_email.delay(
                        invitation.invitee.email, invitation.project.title, invite_url
                    )
                )
            except Exception as err:
                raise serializers.ValidationError(
                    {"email": "Unable to send invitation right now. Please retry."}
                ) from err

        return invitation


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
            return "owner"
        return "admin" if obj.is_admin else "member"
