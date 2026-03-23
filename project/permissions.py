from rest_framework import permissions

from .models import MemberStatus, ProjectMember


class IsProjectMember(permissions.BasePermission):
    """
    Allows access only to users who are members of the specific project.
    """

    def has_permission(self, request, view):
        pid = view.kwargs.get("project_id")

        if not pid:
            return True

        return ProjectMember.objects.filter(project_id=pid, user=request.user).exists()


class CanManageProjectMember(permissions.BasePermission):
    """
    Custom permission to determine if a user can update or remove a member.
    """

    def has_permission(self, request, view):
        project_id = view.kwargs.get("project_id")
        return ProjectMember.objects.filter(
            project_id=project_id, user=request.user, status=MemberStatus.MEMBER
        ).exists()

    def has_object_permission(self, request, view, obj):
        project = obj.project
        requester = request.user
        if project.owner == requester:
            return True

        requester_membership = ProjectMember.objects.filter(
            project=project, user=requester
        ).first()

        if requester_membership and requester_membership.is_admin:
            return not obj.is_admin

        return False
