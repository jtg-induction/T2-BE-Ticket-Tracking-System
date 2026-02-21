from rest_framework import permissions

from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel


class IsProjectAdminOrReadOnly(permissions.BasePermission):
    """
    Project-level permission policy to manage access based on membership and roles.

    Access Rules:
    1. **Authentication**: User must be authenticated.
    2. **Project Context**: If no project ID is provided in the URL, access is granted
       (falls back to other permissions).
    3. **Membership**: User must be an active project member or the project owner to
       access any data.
    4. **Read Access**: All active members/owners have access to GET, HEAD, and OPTIONS.
    5. **Write Access (Full)**: Only the project owner or a member with 'Admin'
       privileges can perform POST, PUT, or DELETE.
    6. **Write Access (Restricted)**: Regular members can only use PATCH if they are
       updating the 'status' field exclusively.
    """

    def has_permission(self, request, view):
        """
        Determines if the request has the necessary project-level authorization.

        Args:
            request: The current DRF request object.
            view: The view instance being accessed.

        Returns:
            bool: True if access is authorized, False otherwise.
        """
        project_pk = view.kwargs.get("project_pk")
        user = request.user

        if not user.is_authenticated:
            return False

        if not project_pk:
            return True

        membership = ProjectMember.objects.filter(
            project_id=project_pk, user=user, status=MemberStatus.MEMBER
        ).first()

        is_owner = ProjectModel.objects.filter(id=project_pk, owner=user).exists()

        if not membership and not is_owner:
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        if request.method == "PATCH" and membership:
            update_fields = set(request.data.keys())

            if update_fields == {"status"}:
                return True

        return is_owner or (membership and membership.is_admin)
