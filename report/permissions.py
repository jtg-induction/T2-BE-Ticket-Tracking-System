from rest_framework import permissions

from project.enums import MemberStatus
from project.models import Project, ProjectMember


class IsProjectMember(permissions.BasePermission):
    """
    Permission to allow access only if the user is the project owner
    or an active member of the project.
    """

    def has_permission(self, request, view):
        project_id = request.query_params.get("project")

        if not project_id:
            return True

        if Project.objects.filter(id=project_id, owner=request.user).exists():
            return True

        return ProjectMember.objects.filter(
            project_id=project_id, user=request.user, status=MemberStatus.MEMBER
        ).exists()
