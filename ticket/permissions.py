from django.db.models import Q
from rest_framework import permissions

from project.enums import MemberStatus
from project.models import ProjectMember


class IsProjectAdminOrReadOnly(permissions.BasePermission):
    """
    Handles Project-level and Ticket-level authorization.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False

        if view.action == "list_all_tickets":
            return True

        project_pk = view.kwargs.get("project_pk")
        if not project_pk:
            return True

        has_access = ProjectMember.objects.filter(
            Q(project_id=project_pk, user=user, status=MemberStatus.MEMBER)
            | Q(project_id=project_pk, project__owner=user)
        ).exists()

        if request.method == "LIST":
            return has_access

        return True

    def has_object_permission(self, request, view, obj):
        """
        Specific CRUD logic for Ticket objects.
        Runs for: retrieve, update, partial_update, destroy.
        """
        user = request.user

        if obj.project.owner == user:
            return True

        membership = ProjectMember.objects.filter(
            project=obj.project, user=user, status=MemberStatus.MEMBER
        ).first()

        if membership and membership.is_admin:
            return True

        if obj.reporter == user or obj.assignee == user:
            return True

        if request.method in permissions.SAFE_METHODS:
            return membership is not None

        if request.method == "PATCH" and membership:
            return set(request.data.keys()) == {"status"}

        return False
