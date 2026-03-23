from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.renders import StandardizedJSONRenderer
from core.services import JiraProjectService
from core.utils import StandardizedPagination, parse_jira_error

from .enums import MemberStatus, ProjectRole
from .models import ProjectInvitation, ProjectMember, ProjectModel
from .permissions import CanManageProjectMember, IsProjectMember
from .serializers import (
    InviteUserSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
)
from .services import ProjectMembershipService


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


class ProjectInvitationView(viewsets.GenericViewSet):
    """
    Unified ViewSet for managing the Project Invitation lifecycle.

    This ViewSet centralizes the logic for sending invitations to users,
    as well as the subsequent acceptance or rejection of those invitations.
    It coordinates local database updates with external Jira project synchronization.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = InviteUserSerializer

    def _is_admin(self, user, project):
        """
        Check if a user has administrative privileges for a specific project.

        Args:
            user (CustomUser): The user instance to verify.
            project (ProjectModel): The project instance being accessed.

        Returns:
            bool: True if the user is a staff member, the owner, or an admin member.
        """
        return (
            user.is_staff
            or project.owner == user
            or ProjectMember.objects.filter(
                project=project, user=user, is_admin=True, status=MemberStatus.MEMBER
            ).exists()
        )

    @action(detail=True, methods=["post"])
    def invite(self, request, pk=None):
        """
        Send a project invitation to a specific user.

        Verifies that the requester has administrative rights to the project,
        validates the invitee's email, and creates a pending invitation record.

        Args:
            request (Request): The DRF request object containing 'email' and 'is_admin'.
            pk (uuid): The primary key of the Project to invite the user to.

        Returns:
            Response: 201 Created on success, 403 Forbidden if unauthorized,
                     or 400 Bad Request if validation fails.
        """
        project = get_object_or_404(ProjectModel, pk=pk)

        if not self._is_admin(request.user, project):
            return Response(
                {"detail": "Only project admins can invite users."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "project_id": project.id},
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Invitation sent successfully."}, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["post"], url_path="accept/(?P<token>[^/.]+)")
    def accept(self, request, token=None):
        """
        Accept a project invitation using a unique secure token.

        This action performs a dual-sync:
        1. Local: Updates/Creates the ProjectMember record.
        2. Remote: Adds the user to the corresponding Jira project via JiraProjectService.

        Args:
            request (Request): The DRF request object (must be the intended invitee).
            token (str): The unique UUID/string token associated with the invitation.

        Returns:
            Response: 200 OK on success, 404 Not Found for invalid tokens,
                     403 Forbidden if accessed by the wrong user, or 502 Bad Gateway
                     if the Jira synchronization fails.
        """
        try:
            invitation = ProjectInvitation.objects.get(token=token)
        except ProjectInvitation.DoesNotExist:
            return Response(
                {"detail": "Invalid token"}, status=status.HTTP_404_NOT_FOUND
            )

        if not invitation.is_valid or invitation.invitee != request.user:
            return Response(
                {"detail": "Forbidden or expired invitation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            JiraProjectService.add_user_to_jira_project(
                user=invitation.invited_by,
                project=invitation.project,
                invitee=invitation.invitee,
                role=invitation.is_admin,
            )
        except Exception as e:
            clear_error = parse_jira_error(e)
            return Response(
                {"detail": clear_error},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            with transaction.atomic():
                ProjectMember.objects.update_or_create(
                    project=invitation.project,
                    user=invitation.invitee,
                    defaults={
                        "is_admin": invitation.is_admin,
                        "status": MemberStatus.MEMBER,
                    },
                )

                invitation.is_accepted = True
                invitation.save()

            return Response({"detail": "Joined project successfully."})
        except Exception as e:
            return Response(
                {"detail": f"{str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"], url_path="reject/(?P<token>[^/.]+)")
    def reject(self, request, token=None):
        """
        Reject and delete a pending project invitation.

        Args:
            request (Request): The DRF request object.
            token (str): The token of the invitation to be rejected.

        Returns:
            Response: 200 OK on success, 404 Not Found if no pending
                     invitation matches the token for this user.
        """
        invitation = ProjectInvitation.objects.filter(
            token=token, invitee=request.user, is_accepted=False
        ).first()

        if not invitation:
            return Response(
                {"detail": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND
            )

        invitation.delete()
        return Response({"detail": "Invitation rejected."})


class ProjectMemberViewSet(viewsets.GenericViewSet):
    """
    ViewSet for managing project membership, roles, and ownership.
    """

    serializer_class = ProjectMemberSerializer
    lookup_field = "user_id"
    lookup_url_kwarg = "user_id"

    def get_queryset(self):
        project_id = self.kwargs.get("project_id")
        user = self.request.user

        return (
            ProjectMember.objects.filter(
                project_id=project_id, status=MemberStatus.MEMBER
            )
            .select_related("user", "project")
            .annotate(
                priority=Case(
                    When(user=user, then=Value(1)),
                    When(user_id=F("project__owner_id"), then=Value(2)),
                    When(is_admin=True, then=Value(3)),
                    default=Value(4),
                    output_field=IntegerField(),
                )
            )
            .order_by("priority", "user__email")
        )

    def get_permissions(self):
        """
        Applies IsProjectMember to general actions and
        CanManageProjectMember to destructive/role actions.
        """
        if self.action in ["update_role", "destroy"]:
            return [IsAuthenticated(), CanManageProjectMember()]
        return [IsAuthenticated(), IsProjectMember()]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="update-role")
    def update_role(self, request, project_id=None, user_id=None):
        """
        Coordinates role updates between Jira and Local DB via Services.
        """
        project = get_object_or_404(ProjectModel, id=project_id)
        target_member = self.get_object()

        role_input = request.data.get("role") or request.data.get("project_role")
        new_role = role_input.lower().strip() if isinstance(role_input, str) else None

        try:
            JiraProjectService.update_user_role_in_jira(
                user=request.user,
                project=project,
                target_user=target_member.user,
                new_role=new_role,
            )

            if new_role == ProjectRole.OWNER:
                ProjectMembershipService.transfer_ownership(
                    project, target_member, request.user
                )
            elif new_role in [ProjectRole.ADMIN, ProjectRole.MEMBER]:
                ProjectMembershipService.update_role(
                    project, target_member, request.user, new_role
                )
            else:
                return Response(
                    {"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST
                )

            return Response({"detail": f"Role updated to {new_role} successfully."})

        except Exception as e:
            return Response(
                {"detail": parse_jira_error(e)}, status=status.HTTP_400_BAD_REQUEST
            )

    def destroy(self, request, project_id=None, user_id=None):
        """
        Handles member removal or departure.
        """
        project = get_object_or_404(ProjectModel, id=project_id)
        target_member = self.get_object()

        message = ProjectMembershipService.remove_or_exit(
            project, target_member, request.user
        )
        return Response({"detail": message})
