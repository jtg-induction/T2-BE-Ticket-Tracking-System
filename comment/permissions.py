from rest_framework import permissions


class CommentPermission(permissions.BasePermission):
    """
    Permission class to restrict comment access and modifications.

    - All authenticated users can view comments (SAFE_METHODS).
    - Modifications (UPDATE, DELETE) are restricted to the original commentator.
    - No modifications are allowed if the associated project is archived.
    """

    def has_permission(self, request, view):
        """
        Check if the user is authenticated for general access.
        """
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """
        Evaluate per-object permissions for specific comment instances.

        Allows read access to any authenticated user. For write operations,
        verifies that the project is not archived and that the requesting
        user is the owner of the comment.
        """
        if request.method in permissions.SAFE_METHODS:
            return True

        if obj.ticket.project.is_archived:
            return False

        return obj.commentator_id == request.user.user_id
