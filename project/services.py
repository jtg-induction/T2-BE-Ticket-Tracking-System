from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from .enums import ProjectRole
from .models import MemberStatus, ProjectMember


class ProjectMembershipService:
    @staticmethod
    def transfer_ownership(project, target_member, current_owner):
        """Handles the logic for transferring project ownership."""
        if project.owner != current_owner:
            raise PermissionDenied("Only the owner can transfer ownership.")

        with transaction.atomic():
            ProjectMember.objects.filter(project=project, user=current_owner).update(
                is_admin=True
            )

            project.owner = target_member.user
            project.save()

            target_member.is_admin = True
            target_member.save()

    @staticmethod
    def update_role(project, target_member, requester, new_role):
        """Handles promotion to Admin or demotion to Member."""
        is_admin_val = new_role == ProjectRole.ADMIN

        if is_admin_val:
            requester_mem = ProjectMember.objects.get(project=project, user=requester)
            if not (project.owner == requester or requester_mem.is_admin):
                raise PermissionDenied("No permission to promote.")

        else:
            if project.owner != requester:
                raise PermissionDenied("Only owner can demote admins.")

        with transaction.atomic():
            target_member.is_admin = is_admin_val
            target_member.save()

    @staticmethod
    def remove_or_exit(project, target_member, requester):
        """Handles a user leaving or being kicked from a project."""

        if requester == target_member.user:
            if project.owner == requester:
                raise ValidationError(
                    {"detail": "Owner cannot leave without transferring ownership."}
                )
            msg = "You have left the project."

        else:
            msg = "Member removed successfully."

        target_member.status = MemberStatus.LEFT
        target_member.save()
        return msg
