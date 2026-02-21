from rest_framework import permissions

from .models import ProjectMember


class IsProjectMember(permissions.BasePermission):
    """
    Allows access only to users who are members of the specific project.
    """

    def has_permission(self, request, view):
        pid = view.kwargs.get("project_id")

        if not pid:
            return True

        return ProjectMember.objects.filter(project_id=pid, user=request.user).exists()
