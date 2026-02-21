from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination

from core.renders import StandardizedJSONRenderer
from core.services import JiraProjectService
from project.enums import MemberStatus
from ticket.models import Ticket

from .models import CommentModel
from .permissions import CommentPermission
from .serializers import CommentSerializer


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class CommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and editing ticket comments.

    Provides standard CRUD actions for CommentModel. All actions are scoped
    to a specific ticket provided via the URL (ticket_pk).
    """

    serializer_class = CommentSerializer
    permission_classes = [CommentPermission]
    pagination_class = StandardResultsSetPagination
    renderer_classes = [StandardizedJSONRenderer]

    def get_queryset(self):
        """
        Retrieve the list of comments for the current ticket.

        Filters comments based on the 'ticket_pk' and ensures the requesting
        user has access to the ticket via project membership, or by being
        the reporter/assignee. Uses select_related to optimize DB queries.
        """
        user = self.request.user
        ticket_id = self.kwargs.get("ticket_pk")

        return (
            CommentModel.objects.filter(
                Q(ticket_id=ticket_id)
                & (
                    Q(
                        ticket__project__memberships__user=user,
                        ticket__project__memberships__status=MemberStatus.MEMBER,
                    )
                    | Q(ticket__reporter=user)
                    | Q(ticket__assignee=user)
                )
            )
            .select_related(
                "ticket",
                "ticket__project",
                "ticket__reporter",
                "ticket__assignee",
                "commentator",
            )
            .distinct()
        )

    def perform_create(self, serializer):
        """
        Create a new comment instance.

        Validates that the target ticket exists and is not archived. The
        commentator is automatically set to the current authenticated user.
        """
        user = self.request.user
        ticket_id = self.kwargs.get("ticket_pk")
        ticket = get_object_or_404(
            Ticket.objects.filter(
                Q(id=ticket_id)
                & Q(project__is_archived=False)
                & (
                    Q(
                        project__memberships__user=user,
                        project__memberships__status=MemberStatus.MEMBER,
                    )
                    | Q(reporter=user)
                    | Q(assignee=user)
                )
            )
            .select_related("project")
            .distinct()
        )

        serializer.save(commentator=user, ticket=ticket)

    def perform_destroy(self, instance):
        """
        Delete a comment instance and sync the deletion with Jira.

        If the comment has a 'jira_id', an external API call is made to Jira
        via JiraProjectService. If the external sync fails, the local
        deletion is aborted and a ValidationError is raised.
        """
        user = self.request.user

        if instance.jira_id:
            try:
                success = JiraProjectService.delete_jira_comment(
                    user=user,
                    ticket_instance=instance.ticket,
                    jira_comment_id=instance.jira_id,
                )

                if not success:
                    raise Exception("Jira API returned a failure status.")

            except Exception as e:
                from rest_framework import serializers

                raise serializers.ValidationError(
                    {
                        "detail": f"Deletion failed: Could not sync with Jira. Error: {str(e)}"
                    }
                )

        instance.delete()
