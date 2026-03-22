from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from comment.tasks import sync_comments_in_batches
from config.celery import app
from core.services import JiraProjectService
from core.utils import parse_jira_error
from notifications.models import Notifications
from notifications.tasks import (
    run_assignee_notification,
    run_deadline_notification,
    run_status_notification,
)
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
    is_subscribed = serializers.SerializerMethodField()

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

    def get_is_subscribed(self, obj):
        is_subscribed = getattr(obj, "is_subscribed", None)
        if is_subscribed is not None:
            return is_subscribed

        user = self.context.get("request").user
        if user and user.is_authenticated:
            return Notifications.objects.filter(
                ticket=obj, subscriber=user, is_deleted=False
            ).exists()
        return False

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

        user = self.context["request"].user
        reporter = validated_data.get("reporter")
        if not reporter:
            reporter = user
        validated_data["reporter"] = reporter
        project = validated_data["project"]
        assignee = validated_data.get("assignee")
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
        except Exception as e:
            clean_error = parse_jira_error(e)
            raise serializers.ValidationError({"detail": clean_error})

        validated_data["jira_id"] = jira_response.get("key")

        with transaction.atomic():
            ticket = super().create(validated_data)

            # automatically subscribing reporter and assignee
            subscribers_to_add = {reporter}
            if assignee:
                subscribers_to_add.add(assignee)

            notification_instances = [
                Notifications(ticket=ticket, subscriber=sub)
                for sub in subscribers_to_add
            ]

            Notifications.objects.bulk_create(notification_instances)

            # send email to assignee
            if assignee:
                transaction.on_commit(
                    lambda: run_assignee_notification.delay(ticket.id)
                )

            if deadline:
                remainder_time = deadline - timedelta(days=1)

                if remainder_time < timezone.now():
                    remainder_time = deadline - timedelta(hours=2)

                if remainder_time > timezone.now():
                    task_result = run_deadline_notification.apply_async(
                        args=[ticket.id], eta=remainder_time
                    )
                    ticket.deadline_task_id = task_result.id
                    ticket.save(update_fields=["deadline_task_id"])

            return ticket

    def update(self, instance, validated_data):
        user = self.context["request"].user

        # 1. Snapshots for comparison
        old_status = instance.status
        old_deadline = instance.deadline
        old_assignee = instance.assignee
        old_task_id = instance.deadline_task_id

        new_status = validated_data.get("status")
        new_deadline = validated_data.get("deadline")
        new_assignee = validated_data.get("assignee")

        # 2. Update Metadata
        if new_status and new_status != old_status:
            validated_data["status_updated_from"] = old_status
            validated_data["status_updated_at"] = timezone.now()
            validated_data["status_updated_by"] = user
            if new_status == Status.CLOSED:
                validated_data["completed_at"] = timezone.now()

        validated_data["updated_by"] = user

        # 3. Jira Sync
        try:
            JiraProjectService.update_jira_task(
                user=user, ticket_instance=instance, validated_data=validated_data
            )
        except Exception as e:
            raise serializers.ValidationError({"detail": parse_jira_error(e)})

        # 4. Atomic Database Updates
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            # Auto-subscribe new assignee
            if new_assignee and new_assignee != old_assignee:
                Notifications.objects.get_or_create(
                    ticket=instance, subscriber=new_assignee
                )

            # Revoke old task and schedule new one
            if new_deadline and new_deadline != old_deadline:
                if old_task_id:
                    app.control.revoke(old_task_id, terminate=True)

                remainder_time = new_deadline - timedelta(days=1)
                if remainder_time < timezone.now():
                    remainder_time = new_deadline - timedelta(hours=2)

                if remainder_time > timezone.now():
                    new_task = run_deadline_notification.apply_async(
                        args=[instance.id], eta=remainder_time
                    )
                    instance.deadline_task_id = new_task.id
                else:
                    instance.deadline_task_id = None

            instance.save()

            # 5. TRIGGER NOTIFICATIONS
            if new_status and new_status != old_status:
                transaction.on_commit(
                    lambda: run_status_notification.delay(instance.id)
                )

            if new_assignee and new_assignee != old_assignee:
                transaction.on_commit(
                    lambda: run_assignee_notification.delay(instance.id)
                )

        return instance

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

        sync_comments_in_batches.delay(ticket.id, user.user_id, project.id)

        return ticket, created
