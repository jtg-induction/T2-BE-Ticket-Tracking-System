from rest_framework import permissions

from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel


class IsProjectAdmin(permissions.BasePermission):
    """
    Allows access if the user is the project owner or a member with admin status.
    """

    def has_object_permission(self, request, view, obj):
        project = obj if isinstance(obj, ProjectModel) else obj.project

        if project.owner == request.user:
            return True

        return ProjectMember.objects.filter(
            project=project,
            user=request.user,
            is_admin=True,
            status=MemberStatus.MEMBER,
        ).exists()


class IsProjectOwner(permissions.BasePermission):
    """
    Strict permission: only the project owner (creator) can perform the action.
    """

    def has_object_permission(self, request, view, obj):
        project = obj if isinstance(obj, ProjectModel) else obj.project
        return project.owner == request.user
