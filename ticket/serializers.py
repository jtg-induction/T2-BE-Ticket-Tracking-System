from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from core.services import JiraProjectService
from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from user.serializers import UserSerializer

from .enums import Category, Status
from .models import Ticket


class TicketSerializer(serializers.ModelSerializer):
    """
    Serializer for Ticket model handling Jira synchronization.

    This serializer manages the full lifecycle of a ticket, including validation
    against project membership, status transition rules, and synchronous
    creation/updates with the external Jira API.
    """

    project = serializers.PrimaryKeyRelatedField(
        queryset=ProjectModel.objects.all(), required=False
    )
    ticket_role = serializers.SerializerMethodField()
    is_project_archived = serializers.BooleanField(
        source="project.is_archived", read_only=True
    )

    class Meta:
        model = Ticket
        fields = "__all__"
        read_only_fields = [
            "id",
            "jira_id",
            "status_updated_at",
            "status_updated_from",
            "status_updated_by",
            "is_project_archived",
        ]

    def validate_status(self, value):
        """
        Ensures only the original reporter can transition a ticket to CLOSED.
        """
        user = self.context["request"].user

        if self.instance and value == Status.CLOSED:
            if user != self.instance.reporter:
                raise serializers.ValidationError(
                    {"status": "You can not close the ticket."}
                )

        return value

    def validate(self, data):
        """
        Cross-field validation for project integrity.

        Checks:
        1. Reporter and Assignee must be active members of the project.
        2. Reporter cannot be modified after creation.
        3. Tickets cannot be edited if the project is archived.
        4. Cross-project moves must stay within the same Jira site.
        """
        project_id = self.context.get("project_id")
        reporter = data.get("reporter")
        assignee = data.get("assignee")

        users_to_verify = []
        if reporter and not self.instance:
            users_to_verify.append(reporter.user_id)
        if assignee:
            users_to_verify.append(assignee.user_id)

        if users_to_verify:
            valid_member_ids = set(
                ProjectMember.objects.filter(
                    project_id=project_id,
                    user_id__in=users_to_verify,
                    status=MemberStatus.MEMBER,
                ).values_list("user_id", flat=True)
            )

            if (
                reporter
                and not self.instance
                and reporter.user_id not in valid_member_ids
            ):
                raise serializers.ValidationError(
                    {"reporter": "User is not a member of this project."}
                )

            if assignee and assignee.user_id not in valid_member_ids:
                raise serializers.ValidationError(
                    {"assignee": "User is not a member of this project."}
                )

        if (
            self.instance
            and "reporter" in data
            and data["reporter"] != self.instance.reporter
        ):
            raise serializers.ValidationError(
                {"reporter": "Reporter cannot be changed."}
            )

        if self.instance and self.instance.project.is_archived:
            raise serializers.ValidationError(
                {"project": "Cannot edit an archived project."}
            )

        new_project = data.get("project")
        if self.instance and new_project and new_project.id != self.instance.project_id:
            if new_project.is_archived:
                raise serializers.ValidationError(
                    {"project": "Target project is archived."}
                )
            if new_project.site_url != self.instance.project.site_url:
                raise serializers.ValidationError(
                    {"project": "Cannot move ticket to a different Jira site."}
                )

        return data

    def create(self, validated_data):
        """
        Creates a ticket locally after successfully creating it in Jira.
        """

        with transaction.atomic():
            user = self.context["request"].user
            reporter = validated_data.get("reporter")
            if not reporter:
                reporter = user
            validated_data["reporter"] = reporter
            project = validated_data["project"]
            deadline = validated_data.get("deadline")
            formatted_deadline = deadline.strftime("%Y-%m-%d") if deadline else None

            try:
                jira_response = JiraProjectService.create_jira_task(
                    user=user,
                    project_instance=project,
                    summary=validated_data["name"],
                    description=validated_data.get("description", ""),
                    reporter_id=reporter.jira_id,
                    category=validated_data["category"],
                    priority=validated_data.get("priority", "Medium"),
                    due_date=formatted_deadline,
                )

                validated_data["jira_id"] = jira_response.get("key")
                return super().create(validated_data)

            except Exception:
                raise serializers.ValidationError(
                    {
                        "Jira synchronization failed. Ticket not created.",
                    }
                )

    def update(self, instance, validated_data):
        """
        Updates local ticket and triggers a corresponding update in Jira.

        Tracks status transition metadata (who, when, and from what status).
        """
        with transaction.atomic():
            user = self.context["request"].user
            new_status = validated_data.get("status")

            if new_status and new_status != instance.status:
                validated_data["status_updated_from"] = instance.status
                validated_data["status_updated_at"] = timezone.now()
                validated_data["status_updated_by"] = user

                if new_status == Status.CLOSED:
                    validated_data["completed_at"] = timezone.now()

            validated_data["updated_by"] = user

            instance = super().update(instance, validated_data)
            try:
                JiraProjectService.update_jira_task(
                    user=user, ticket_instance=instance, validated_data=validated_data
                )

                return instance

            except Exception:
                raise serializers.ValidationError(
                    {
                        "Jira synchronization failed. Local update aborted.",
                    }
                )

    def to_representation(self, instance):
        """
        Expands reporter and assignee IDs into full user objects in the output.
        """
        representation = super().to_representation(instance)

        representation["reporter"] = (
            UserSerializer(instance.reporter, context=self.context).data
            if instance.reporter
            else None
        )

        representation["assignee"] = (
            UserSerializer(instance.assignee, context=self.context).data
            if instance.assignee
            else None
        )

        return representation

    def get_ticket_role(self, obj):
        """
        Calculates the relationship between the requesting user and the ticket.

        Possible roles: reporter, assignee, admin, member, guest, none.
        """
        user = self.context.get("request").user
        if not user or user.is_anonymous:
            return "guest"

        if user == obj.reporter:
            return "reporter"

        membership = self.context.get("user_membership")

        if membership and membership.is_admin:
            return "admin"

        if user == obj.assignee:
            return "assignee"

        if membership:
            return "member"

        return "none"


class JiraImportSerializer(serializers.Serializer):
    """
    Handles the full import lifecycle for a single external Jira ticket.

    Retrieves ticket data from Jira Cloud, maps it to the local model schema,
    and validates that the required users (reporter) exist in the local system.
    """

    jira_id = serializers.CharField(max_length=255)
    category = serializers.ChoiceField(
        choices=Category.choices, default=Category.DEVELOPMENT
    )

    def validate_jira_id(self, value):
        """
        Prevents duplicate imports of the same Jira ticket.
        """
        if Ticket.objects.filter(jira_id=value).exists():
            raise serializers.ValidationError("This ticket has already been imported.")
        return value

    def save(self, user, project, mapper_func):
        """
        Fetches the ticket from Jira, maps fields, and persists to local DB.

        Args:
            user: The user performing the import.
            project: The project instance to link the ticket to.
            mapper_func: Utility function to convert Jira JSON to Ticket instance.

        Returns:
            tuple: (Ticket instance, boolean created status)
        """
        jira_id = self.validated_data["jira_id"]

        response_data = JiraProjectService.search_jira_tickets(
            user=user,
            project_instance=project,
            jql_query=f"key = {jira_id} ",
            maxResults=1,
        )

        issues = response_data.get("issues", [])

        if not issues:
            raise serializers.ValidationError({"Ticket not found or no access."})

        issue_data = issues[0]

        ticket_instance = mapper_func(issue_data, project)
        User = get_user_model()
        assignee = None
        if ticket_instance._jira_assignee_id:
            assignee = User.objects.filter(
                jira_id=ticket_instance._jira_assignee_id
            ).first()

        reporter = None
        if ticket_instance._jira_reporter_id:
            reporter = User.objects.filter(
                jira_id=ticket_instance._jira_reporter_id
            ).first()

            if not reporter:
                raise serializers.ValidationError(
                    {
                        "reporter": "The reporter of this ticket is not part of our environment"
                    }
                )

        ticket, created = Ticket.objects.update_or_create(
            jira_id=ticket_instance.jira_id,
            defaults={
                "name": ticket_instance.name,
                "description": ticket_instance.description,
                "project": project,
                "status": ticket_instance.status,
                "priority": ticket_instance.priority,
                "category": self.validated_data["category"],
                "assignee": assignee,
                "reporter": reporter,
            },
        )
        return ticket, created
