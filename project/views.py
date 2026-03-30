from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.constants import PAGE_SIZE
from core.renders import StandardizedJSONRenderer
from core.utils import StandardizedPagination
from project.constants import ProjectMessages
from project.enums import MemberStatus, ProjectRole
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
    page_size = PAGE_SIZE
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
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    filterset_fields = {
        "site_url": ["exact", "icontains"],
        "is_archived": ["exact"],
    }

    search_fields = ["title", "description", "jira_project_key"]

    ordering_fields = ["created_at", "title", "jira_project_key"]

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

        if self.request.query_params.get("archived", None):
            show_archived = (
                self.request.query_params.get("archived", "false").lower() == "true"
            )
            base_qs.filter(is_archived=show_archived)
        return base_qs


class ProjectInvitationView(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InviteUserSerializer

    def invite(self, request, pk=None):
        project = get_object_or_404(ProjectModel, pk=pk)
        if not IsProjectAdmin().has_object_permission(request, self, project):
            raise PermissionDenied(ProjectMessages.ADMIN_REQUIRED)

        serializer = self.get_serializer(
            data=request.data, context={"project_id": project.id, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": ProjectMessages.INVITE_SENT}, status=status.HTTP_201_CREATED
        )

    def accept(self, request, token=None):
        ProjectService.accept_invitation(token, request.user)
        return Response({"detail": ProjectMessages.JOINED_SUCCESS})

    def reject(self, request, token=None):
        ProjectService.reject_invitation(token, request.user)
        return Response({"detail": ProjectMessages.INVITE_REJECTED})


class ProjectMemberViewSet(viewsets.GenericViewSet):
    serializer_class = ProjectMemberSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardizedPagination
    renderer_classes = [StandardizedJSONRenderer]

    filter_backends = [filters.SearchFilter]
    search_fields = ["user__first_name", "user__last_name", "user__email"]

    def get_queryset(self):
        return ProjectService.get_annotated_members(
            self.kwargs.get("project_id"), self.request.user
        )

    def list(self, request, project_id=None):
        queryset = self.filter_queryset(self.get_queryset())
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
            ProjectMember,
            project=project,
            user=request.user,
            status=MemberStatus.MEMBER,
        )

        role_input = request.data.get("role") or request.data.get("projectRole")
        new_role = role_input.lower().strip() if isinstance(role_input, str) else ""

        if new_role == ProjectRole.OWNER and project.owner != request.user:
            raise PermissionDenied(ProjectMessages.OWNER_ONLY_TRANSFER)

        if new_role == ProjectRole.ADMIN and not (
            project.owner == request.user or requester_membership.is_admin
        ):
            raise PermissionDenied(ProjectMessages.PROMOTION_DENIED)

        if new_role == ProjectRole.MEMBER and project.owner != request.user:
            raise PermissionDenied(ProjectMessages.DEMOTION_DENIED)

        if new_role not in ProjectRole.values:
            return Response(
                {"detail": ProjectMessages.INVALID_ROLE},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ProjectService.update_member_role(project, request.user, user_id, new_role)
        return Response({"detail": f"Role updated to {new_role}."})

    def remove_user(self, request, project_id=None, user_id=None):
        project = get_object_or_404(ProjectModel, id=project_id)
        target_member = get_object_or_404(
            ProjectMember,
            project=project,
            user_id=user_id,
            status=MemberStatus.MEMBER,
        )

        is_self = str(request.user.user_id) == str(user_id)
        if not is_self:
            requester_mem = get_object_or_404(
                ProjectMember,
                project=project,
                user=request.user,
                status=MemberStatus.MEMBER,
            )
            can_kick = (project.owner == request.user) or (
                requester_mem.is_admin and not target_member.is_admin
            )
            if not can_kick:
                raise PermissionDenied(ProjectMessages.PERMISSION_DENIED)

        ProjectService.remove_member(project, request.user, user_id)
        msg = (
            ProjectMessages.LEFT_PROJECT if is_self else ProjectMessages.MEMBER_REMOVED
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
