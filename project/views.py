from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.renders import StandardizedJSONRenderer
from core.utils import StandardizedPagination

from .enums import MemberStatus
from .models import ProjectMember, ProjectModel
from .serializers import ProjectSerializer


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
