from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.renders import StandardizedJSONRenderer
from core.services import JiraProjectService
from core.utils import parse_jira_error
from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel

from .models import Ticket
from .permissions import IsProjectAdminOrReadOnly
from .serializers import JiraImportSerializer, TicketSerializer
from .utils import map_jira_to_ticket


class TicketPagination(PageNumberPagination):
    page_query_param = "page"
    page_size_query_param = "pageSize"
    page_size = 10
    max_page_size = 100


class TicketViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Ticket operations within a project context.
    """

    serializer_class = TicketSerializer
    permission_classes = [IsProjectAdminOrReadOnly]
    pagination_class = TicketPagination
    renderer_classes = [StandardizedJSONRenderer]

    def get_queryset(self):
        """
        Retrieves the list of tickets for a specific project.

        Optimizes the query by selecting related user and project objects to
        prevent N+1 database hits. Also pre-fetches the current user's
        project membership to facilitate role-based logic in the serializer.
        """
        user = self.request.user

        queryset = Ticket.objects.filter(
            project_id=self.kwargs["project_pk"], is_deleted=False
        ).select_related("reporter", "assignee", "project", "project__owner")

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        self.user_membership = ProjectMember.objects.filter(
            user=user, project_id=self.kwargs["project_pk"], status=MemberStatus.MEMBER
        ).first()

        return queryset

    def get_serializer_context(self):
        """
        Extends the serializer context with project-specific metadata.

        Injects the current project ID and the pre-fetched user membership
        object so the serializer can calculate roles without additional DB queries.
        """
        context = super().get_serializer_context()
        context.update(
            {
                "project_id": self.kwargs.get("project_pk"),
                "user_membership": getattr(self, "user_membership", None),
            }
        )
        return context

    def perform_create(self, serializer):
        """
        Persists a new ticket instance linked to the current project.
        """
        project_instance = get_object_or_404(ProjectModel, pk=self.kwargs["project_pk"])
        serializer.save(project=project_instance)

    @action(detail=False, methods=["get"], url_path="all-tickets")
    def list_all_tickets(self, request, project_pk=None):
        """
        Retrieves all tickets across the system where the requesting user
            is either the reporter or the assignee.
        """
        queryset = Ticket.objects.select_related(
            "reporter", "assignee", "project"
        ).filter(Q(assignee=request.user) | Q(reporter=request.user))

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class JiraTicketViewSet(viewsets.GenericViewSet):
    """
    Generic ViewSet for handling interactions with the external Jira API.

    Provides endpoints for searching tickets directly from Jira Cloud
    and importing specific tickets into the local tracking system.
    """

    serializer_class = TicketSerializer
    renderer_classes = [StandardizedJSONRenderer]

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request, project_pk=None):
        query = request.query_params.get("q", "")
        cursor = request.query_params.get("cursor", None)
        max_results = request.query_params.get("max_results", 50)

        project = get_object_or_404(ProjectModel, pk=project_pk)

        try:
            jira_data = JiraProjectService.search_jira_tickets(
                user=request.user,
                project_instance=project,
                jql_query=query,
                nextPageToken=cursor,
                maxResults=max_results,
            )

            jira_issues = jira_data.get("issues", [])

            remote_keys = [issue.get("key") for issue in jira_issues]

            existing_keys = set(
                Ticket.objects.filter(
                    project=project, jira_id__in=remote_keys
                ).values_list("jira_id", flat=True)
            )

            tickets = []
            for issue in jira_issues:
                ticket_obj = map_jira_to_ticket(issue, project)
                ticket_obj.is_imported = ticket_obj.jira_id in existing_keys
                tickets.append(ticket_obj)

            serializer = self.get_serializer(tickets, many=True)
            return Response(
                {
                    "results": serializer.data,
                    "next": jira_data.get("next_page_token"),
                    "total": jira_data.get("total", 0),
                }
            )

        except Exception as e:
            return Response({"error": parse_jira_error(e)}, status=400)

    @action(detail=False, methods=["post"], url_path="import")
    def import_to_local(self, request, project_pk=None):
        """
        Imports a specific Jira issue into the local database using its Jira Key.
        Ensures the ticket doesn't already exist and that the reporter is
        a registered user in the local environment.
        """
        project = get_object_or_404(ProjectModel, pk=project_pk)

        serializer = JiraImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ticket, created = serializer.save(
                user=request.user, project=project, mapper_func=map_jira_to_ticket
            )

            return Response(
                self.get_serializer(ticket).data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
