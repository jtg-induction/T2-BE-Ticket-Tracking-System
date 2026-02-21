from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.renders import StandardizedJSONRenderer
from core.services import JiraProjectService
from core.utils import StandardizedPagination, parse_jira_error

from .enums import MemberStatus
from .models import ProjectInvitation, ProjectMember, ProjectModel
from .permissions import IsProjectMember
from .serializers import (
    InviteUserSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
)


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
                is_admin=invitation.is_admin,
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
    permission_classes = [IsAuthenticated, IsProjectMember]
    pagination_class = StandardizedPagination
    renderer_classes = [StandardizedJSONRenderer]
    filter_backends = [filters.SearchFilter]
    search_fields = ["user__first_name", "user__last_name", "user__email"]

    def get_queryset(self):
        """
        Retrieves the list of active members for a specific project.

        Annotates the queryset with a 'priority' field to ensure the
        ordering follows a specific hierarchy:
        1. The requesting user (Self)
        2. Project Owner
        3. Project Admins
        4. Regular Members
        """
        project_id = self.kwargs.get("project_id")
        user = self.request.user

        return (
            ProjectMember.objects.filter(
                project_id=project_id, status=MemberStatus.MEMBER
            )
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

    def list(self, request, *args, **kwargs):
        """
        Returns a paginated list of all active members in the project,
        ordered by their role priority and email.
        """
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(data=serializer.data)

    def update_role(self, request, project_id=None, user_id=None):
        """
        Updates the role of a project member.

        Logic:
        - 'owner': Transfers project ownership. Only the current owner can perform this.
        - 'admin': Promotes a member. Requires the requester to be an owner or admin.
        - 'member': Demotes an admin. Only the owner can demote other admins.
        """
        project = get_object_or_404(ProjectModel, id=project_id)
        target_member = get_object_or_404(
            ProjectMember, project=project, user_id=user_id
        )
        current_user = request.user
        requester_membership = get_object_or_404(
            ProjectMember, project=project, user=current_user
        )

        role_input = request.data.get("role") or request.data.get("projectRole")
        new_role = role_input.lower().strip() if isinstance(role_input, str) else None

        if new_role == "owner":
            if project.owner != current_user:
                return Response(
                    {"detail": "Only the owner can transfer ownership."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            try:
                JiraProjectService.update_user_role_in_jira(
                    user=current_user,
                    project=project,
                    target_user=target_member.user,
                    new_role=new_role,
                )
            except Exception as e:
                clean_error = parse_jira_error(e)
                return Response(
                    {"detail": clean_error},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                ProjectMember.objects.filter(project=project, user=current_user).update(
                    is_admin=True
                )
                project.owner = target_member.user
                project.save()
                target_member.is_admin = True
                target_member.save()

            return Response({"detail": "Ownership transferred successfully."})

        if new_role in ["admin", "member"]:
            if new_role == "admin":
                if not (project.owner == current_user or requester_membership.is_admin):
                    return Response(
                        {"detail": "No permission to promote."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                is_admin_val = True
            else:
                if project.owner != current_user:
                    return Response(
                        {"detail": "Only owner can demote admins."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                is_admin_val = False

            try:
                JiraProjectService.update_user_role_in_jira(
                    user=current_user,
                    project=project,
                    target_user=target_member.user,
                    new_role=new_role,
                )
            except Exception as e:
                clean_error = parse_jira_error(e)
                return Response(
                    {"detail": clean_error},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                target_member.is_admin = is_admin_val
                target_member.save()

            return Response({"detail": f"Role updated to {new_role}."})

        return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, project_id=None, user_id=None):
        """
        Handles member removal or voluntary exit from a project.

        Logic:
        1. If a user is removing themselves:
           - They cannot leave if they are the Project Owner (must transfer first).
        2. If a user is removing someone else (kicking):
           - Owners can remove anyone.
           - Admins can only remove regular members (cannot remove other admins or the owner).
        """
        project = get_object_or_404(ProjectModel, id=project_id)
        target_member = get_object_or_404(
            ProjectMember, project=project, user_id=user_id
        )
        requester = request.user

        if str(requester.user_id) == str(user_id):
            if project.owner == requester:
                return Response(
                    {"detail": "Owner cannot leave without transferring ownership."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            target_member.status = MemberStatus.LEFT
            target_member.save()
            return Response({"detail": "You have left the project."})

        requester_membership = get_object_or_404(
            ProjectMember, project=project, user=requester
        )

        can_kick = (project.owner == requester) or (
            requester_membership.is_admin and not target_member.is_admin
        )

        if not can_kick:
            return Response(
                {"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN
            )

        target_member.status = MemberStatus.LEFT
        target_member.save()
        return Response({"detail": "Member removed successfully."})
