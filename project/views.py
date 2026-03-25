from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.renders import StandardizedJSONRenderer
from core.utils import StandardizedPagination
from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from project.permissions import IsProjectAdmin
from project.serializers import (
    InviteUserSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
    ProjectUserMembershipSerializer,
)
from project.services import ProjectService


class UserCursorPagination(CursorPagination):
    page_size = 5
    ordering = ("first_name", "pk")


class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Project operations.

    Provides endpoints for listing, retrieving, creating, and updating projects.
    """

    queryset = ProjectModel.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardizedPagination

    def get_permissions(self):
        if self.action in ["partial_update", "update"]:
            return [IsAuthenticated(), IsProjectAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        """
        Returns the list of projects accessible to the current user.

        Returns:
            QuerySet: A distinct queryset of ProjectModel instances.
        """
        user = self.request.user
        base_qs = ProjectModel.objects.filter(
            memberships__user=user, memberships__status=MemberStatus.MEMBER
        ).distinct()

        show_archived = (
            self.request.query_params.get("archived", "true").lower() == "true"
        )
        return base_qs.filter(is_archived=show_archived)


class ProjectInvitationView(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InviteUserSerializer

    def invite(self, request, pk=None):
        project = get_object_or_404(ProjectModel, pk=pk)
        if not IsProjectAdmin().has_object_permission(request, self, project):
            raise PermissionDenied("Admin rights required.")

        serializer = self.get_serializer(
            data=request.data, context={"project_id": project.id, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Invitation sent."}, status=status.HTTP_201_CREATED)

    def accept(self, request, token=None):
        ProjectService.accept_invitation(token, request.user)
        return Response({"detail": "Joined successfully."})

    def reject(self, request, token=None):
        ProjectService.reject_invitation(token, request.user)
        return Response({"detail": "Invitation rejected."})


class ProjectMemberViewSet(viewsets.GenericViewSet):
    serializer_class = ProjectMemberSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardizedPagination
    renderer_classes = [StandardizedJSONRenderer]

    def get_queryset(self):
        return ProjectService.get_annotated_members(
            self.kwargs.get("project_id"), self.request.user
        )

    def list(self, request, project_id=None):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page or queryset, many=True)
        return (
            self.get_paginated_response(serializer.data)
            if page
            else Response(serializer.data)
        )

    def update_role(self, request, project_id=None, user_id=None):
        project = get_object_or_404(ProjectModel, id=project_id)
        requester_membership = get_object_or_404(
            ProjectMember, project=project, user=request.user
        )

        role_input = request.data.get("role") or request.data.get("projectRole")
        new_role = role_input.lower().strip() if isinstance(role_input, str) else ""

        if new_role == "owner" and project.owner != request.user:
            raise PermissionDenied("Only the owner can transfer ownership.")

        if new_role == "admin" and not (
            project.owner == request.user or requester_membership.is_admin
        ):
            raise PermissionDenied("No permission to promote.")

        if new_role == "member" and project.owner != request.user:
            raise PermissionDenied("Only the owner can demote admins.")

        if new_role not in ["owner", "admin", "member"]:
            return Response(
                {"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST
            )

        ProjectService.update_member_role(project, request.user, user_id, new_role)
        return Response({"detail": f"Role updated to {new_role}."})

    def remove_user(self, request, project_id=None, user_id=None):
        project = get_object_or_404(ProjectModel, id=project_id)
        target_member = get_object_or_404(
            ProjectMember, project=project, user_id=user_id
        )

        is_self = str(request.user.user_id) == str(user_id)
        if not is_self:
            requester_mem = get_object_or_404(
                ProjectMember, project=project, user=request.user
            )
            can_kick = (project.owner == request.user) or (
                requester_mem.is_admin and not target_member.is_admin
            )
            if not can_kick:
                raise PermissionDenied("Permission denied.")

        ProjectService.remove_member(project, request.user, user_id)
        msg = (
            "You have left the project." if is_self else "Member removed successfully."
        )
        return Response({"detail": msg}, status=status.HTTP_200_OK)

    def list_all_users(self, request, project_id=None):
        search = request.query_params.get("search")
        queryset = ProjectService.get_all_users_with_membership_flag(project_id, search)

        paginator = UserCursorPagination()
        page = paginator.paginate_queryset(queryset, request)

        serializer = ProjectUserMembershipSerializer(
            page or queryset, many=True, context=self.get_serializer_context()
        )
        return (
            paginator.get_paginated_response(serializer.data)
            if page
            else Response(serializer.data)
        )
