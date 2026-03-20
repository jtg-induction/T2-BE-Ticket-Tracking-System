from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Max, Min, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.utils import timezone
from rest_framework import serializers

from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from ticket.enums import Priority, Status
from ticket.models import Ticket

User = get_user_model()


class ReportSerializer(serializers.Serializer):
    """
    This serializer does analytics, if pulls
    ticket data, calculates efficiency metrics, and groups things by
    status and priority so we can show them in the report.
    """

    efficiency_stats = serializers.SerializerMethodField()
    priority_stats = serializers.SerializerMethodField()
    status_stats = serializers.SerializerMethodField()
    timeline_stats = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()
    detailed_tickets = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        self.include_details = kwargs.pop("include_details", False)
        super().__init__(*args, **kwargs)
        if not self.include_details:
            self.fields.pop("detailed_tickets")

    def validate(self, attrs):
        """
        Check if the project exists and make sure the person asking for
        detailed data actually has the right to see it (Admins or self).
        """
        request = self.context.get("request")
        user = request.user
        params = request.query_params

        project_id = params.get("project")
        if project_id and not ProjectModel.objects.filter(id=project_id).exists():
            raise serializers.ValidationError("Project not found.")

        if self.include_details:
            target_user_id = params.get("user")
            target_users_list = [
                u for u in params.get("users", "").split(",") if u.strip()
            ]

            is_self = False
            if not project_id:
                requested_ids = target_users_list
                if target_user_id:
                    requested_ids.append(target_user_id)
                if not requested_ids or (
                    len(requested_ids) == 1 and requested_ids[0] == str(user.user_id)
                ):
                    is_self = True

            is_admin = False
            if project_id:
                project = ProjectModel.objects.get(id=project_id)
                is_admin = (
                    user.is_staff
                    or project.owner == user
                    or ProjectMember.objects.filter(
                        project=project,
                        user=user,
                        is_admin=True,
                        status=MemberStatus.MEMBER,
                    ).exists()
                )

            if not (is_self or is_admin):
                raise serializers.ValidationError(
                    "You don't have permission to see detailed ticket data."
                )
        return attrs

    def get_metadata(self, obj):
        """
        Gathers basic info for the report header, like which project
        we're looking at and the timeframe for the data.
        """
        request = self.context.get("request")
        params = request.query_params

        start = params.get("start_date", "Beginning")
        end = params.get("end_date", "Present")
        project_id = params.get("project")

        project_name = "All Projects"
        if project_id:
            p = ProjectModel.objects.filter(id=project_id).first()
            project_name = p.title if p else "Unknown"

        return {
            "project_title": project_name,
            "generated_by": request.user.email,
            "date_range": f"{start} — {end}",
            "generated_at": timezone.now().strftime("%Y-%m-%d %H:%M"),
        }

    def get_detailed_tickets(self, obj):
        """
        Pulls the full list of tickets with extra details like emails
        and project names. It also calculates if a ticket 'spilled'
        past its deadline.
        """
        qs = self.get_base_queryset()
        tickets = list(
            qs.values(
                "jira_id",
                "name",
                "status",
                "priority",
                "category",
                "created_at",
                "updated_at",
                "completed_at",
                "deadline",
                project_title=F("project__title"),
                assignee_email=F("assignee__email"),
                assignee_name=F("assignee__first_name"),
                reporter_email=F("reporter__email"),
            )
        )

        now = timezone.now()
        for t in tickets:
            deadline = t.get("deadline")
            comp_at = t.get("completed_at")
            if deadline:
                ref_time = comp_at if comp_at else now
                t["is_spilled"] = ref_time > deadline
            else:
                t["is_spilled"] = False
        return tickets

    def get_base_queryset(self):
        """
        Filters the tickets based on the URL parameters. It handles
        filtering by project, single user, or a list of multiple users.
        """
        request = self.context.get("request")
        params = request.query_params
        project_id = params.get("project")
        user_id = params.get("user")
        user_ids_str = params.get("users")

        queryset = Ticket.objects.all()
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        if user_ids_str:
            ids = [uid.strip() for uid in user_ids_str.split(",") if uid.strip()]
            queryset = queryset.filter(assignee_id__in=ids)
        elif user_id:
            queryset = queryset.filter(assignee_id=user_id)
        elif not project_id:
            queryset = queryset.filter(assignee=request.user)

        return queryset

    def get_priority_stats(self, obj):
        """Groups tickets by priority and counts them."""
        qs = self.get_base_queryset()
        stats = dict(qs.values_list("priority").annotate(total=Count("id")))
        return [
            {"count": stats.get(p.value, 0), "name": p.label, "priority_key": p.value}
            for p in Priority
        ]

    def get_status_stats(self, obj):
        """Groups tickets by their current status and counts them."""
        qs = self.get_base_queryset()
        stats = dict(qs.values_list("status").annotate(total=Count("id")))
        return [
            {"count": stats.get(s.value, 0), "name": s.label, "status_key": s.value}
            for s in Status
        ]

    def get_efficiency_stats(self, obj):
        """
        Calculates how we're doing with deadlines, checks how many
        tickets were completed on time vs. missed or still open.
        """
        qs = self.get_base_queryset()
        priority_map = {
            p.label: Count("id", filter=Q(priority=p.value)) for p in Priority
        }

        return [
            {
                **qs.filter(status__in=[Status.DONE, Status.CLOSED]).aggregate(
                    **priority_map
                ),
                "label": "Project Completed",
            },
            {
                **qs.exclude(status__in=[Status.DONE, Status.CLOSED]).aggregate(
                    **priority_map
                ),
                "label": "Project Incomplete",
            },
            {
                **qs.filter(
                    deadline__isnull=False, completed_at__lte=F("deadline")
                ).aggregate(**priority_map),
                "label": "Met Deadline",
            },
            {
                **qs.filter(
                    deadline__isnull=False, completed_at__gt=F("deadline")
                ).aggregate(**priority_map),
                "label": "Missed Deadline",
            },
            {
                **qs.filter(
                    deadline__isnull=True, status__in=[Status.DONE, Status.CLOSED]
                ).aggregate(**priority_map),
                "label": "Completed (No Deadline)",
            },
        ]

    def get_timeline_stats(self, obj):
        """
        Looks at the ticket volume over time. It automatically scales
        the view (days, months, or years) depending on how wide the
        date range is.
        """
        qs = self.get_base_queryset()
        has_deadlines = qs.filter(deadline__isnull=False).exists()
        date_field = "deadline" if has_deadlines else "created_at"

        bounds = qs.aggregate(first=Min(date_field), last=Max(date_field))
        start, end = bounds["first"], bounds["last"]

        if not start or not end:
            return []

        days_delta = (end - start).days
        if days_delta <= 90:
            trunc, fmt = TruncDate(date_field), "%b %d"
        elif days_delta <= 730:
            trunc, fmt = TruncMonth(date_field), "%b %Y"
        else:
            trunc, fmt = TruncYear(date_field), "%Y"

        priority_map = {
            p.label: Count("id", filter=Q(priority=p.value)) for p in Priority
        }
        stats = (
            qs.annotate(period=trunc)
            .values("period")
            .annotate(**priority_map)
            .order_by("period")
        )

        return [
            {
                **item,
                "label": item["period"].strftime(fmt)
                if isinstance(item["period"], (datetime, date))
                else "N/A",
            }
            for item in stats
        ]
