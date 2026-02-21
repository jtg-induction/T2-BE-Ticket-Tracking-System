from django.db import transaction
from django.db.models import Q
from rest_framework import status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.renders import StandardizedJSONRenderer
from core.services import JiraProjectService
from core.utils import StandardizedPagination

from .enums import MemberStatus
from .models import ProjectInvitation, ProjectMember, ProjectModel
from .serializers import InviteUserSerializer, ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Project operations.

    Provides endpoints for listing, retrieving, creating, and updating projects.
    """

    queryset = ProjectModel.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardizedPagination
    renderer_classes = [StandardizedJSONRenderer]

    def _can_edit(self, user, project):
        """
        Internal helper to determine if a user has administrative rights to a project.

        Args:
            user (CustomUser): The user requesting to edit.
            project (ProjectModel): The project instance being modified.

        Returns:
            bool: True if editing is permitted, False otherwise.
        """
        return (
            user.is_staff
            or project.owner == user
            or ProjectMember.objects.filter(
                project=project, user=user, is_admin=True, status=MemberStatus.MEMBER
            ).exists()
        )

    def get_queryset(self):
        """
        Returns the list of projects accessible to the current user.

        Returns:
            QuerySet: A distinct queryset of ProjectModel instances.
        """
        user = self.request.user
        base_qs = ProjectModel.objects.filter(
            Q(owner=user) | Q(members=user)
        ).distinct()

        if self.action == "list":
            show_archived = (
                self.request.query_params.get("archived", "false").lower() == "true"
            )
            if show_archived:
                return base_qs.filter(is_archived=True)
            return base_qs.filter(is_archived=False)

        return base_qs

    def partial_update(self, request, *args, **kwargs):
        """
        Partially update project details.

        Checks administrative permissions via `_can_edit` before allowing
        any modifications to the project instance.
        """
        instance = self.get_object()
        if not self._can_edit(request.user, instance):
            raise PermissionDenied("You do not have permission to edit this project.")

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["post"], serializer_class=InviteUserSerializer)
    def invite(self, request, pk=None):
        """
        POST /api/project/{id}/invite/
        """
        project = self.get_object()
        if not (
            request.user.is_staff
            or project.owner_id == request.user.user_id
            or ProjectMember.objects.filter(
                project=project,
                user=request.user,
                is_admin=True,
                status=MemberStatus.MEMBER,
            ).exists()
        ):
            return Response(
                {"detail": "Only project admins can invite users."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(
            data=request.data, context={"project_id": project.id, "request": request}
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Invitation sent successfully."}, status=status.HTTP_201_CREATED
        )


class AcceptInvitationView(views.APIView):
    """
    View to handle the acceptance of a project invitation.

    Validates the unique invitation token, verifies the user's identity,
    and adds the user to the remote Jira project
    and updates the local ProjectMember record.
    """

    permission_classes = [IsAuthenticated]
    renderer_classes = [StandardizedJSONRenderer]

    def post(self, request, token):
        """
        Accepts an invitation via a unique token.

        1. Validates the existence and expiration of the token.
        2. Ensures the requester is the intended invitee.
        3. Synchronizes with Jira API to add the member to the cloud project.
        4. Updates or creates the local ProjectMember instance.
        """
        try:
            invitation = ProjectInvitation.objects.get(token=token)
        except ProjectInvitation.DoesNotExist:
            return Response(
                {"detail": "Invalid token"}, status=status.HTTP_404_NOT_FOUND
            )

        if not invitation.is_valid:
            return Response(
                {"detail": "Invitation expired or already used"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.invitee != request.user:
            return Response(
                {"detail": "This invitation is not for you"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if ProjectMember.objects.filter(
            project=invitation.project,
            user=invitation.invitee,
            status=MemberStatus.MEMBER,
        ).exists():
            invitation.is_accepted = True
            invitation.save()
            return Response({"detail": "You are already a member."})

        try:
            with transaction.atomic():
                JiraProjectService.add_user_to_jira_project(
                    user=invitation.invited_by,
                    project=invitation.project,
                    invitee=invitation.invitee,
                    is_admin=invitation.is_admin,
                )

                ProjectMember.objects.update_or_create(
                    project=invitation.project,
                    user=invitation.invitee,
                    defaults={
                        "is_admin": invitation.is_admin,
                        "status": MemberStatus.MEMBER,
                        "updated_by": invitation.invited_by,
                    },
                )

                invitation.is_accepted = True
                invitation.save()

        except Exception as e:
            print(e)
            return Response(
                {"detail": "Jira sync failed. Please try again later."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"detail": "Successfully joined the project"})


class RejectInvitationView(views.APIView):
    """
    View to handle the rejection of a project invitation.

    Allows an invitee to decline and remove an invitation record
    from their pending list.
    """

    permission_classes = [IsAuthenticated]
    renderer_classes = [StandardizedJSONRenderer]

    def post(self, request, token):
        """
        Rejects and deletes an invitation.

        """
        try:
            invitation = ProjectInvitation.objects.get(token=token, is_accepted=False)
        except ProjectInvitation.DoesNotExist:
            return Response(
                {"detail": "Invalid or expired invitation"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if invitation.invitee != request.user:
            return Response(
                {"detail": "This invitation is not for you"},
                status=status.HTTP_403_FORBIDDEN,
            )

        invitation.delete()

        return Response({"detail": "Invitation rejected successfully"})
