from django.conf import settings
from django.db import transaction
from django.db.models import (
    Case,
    CharField,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Q,
    Value,
    When,
)
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.services import JiraProjectService
from project.enums import MemberStatus
from project.models import ProjectInvitation, ProjectMember
from project.tasks import send_invitation_email
from user.models import CustomUser


class ProjectService:
    @staticmethod
    def create_invitation(project, invited_by, invitee, is_admin):
        """
        Creates a project invitation and dispatches the email task.
        Uses invitee user object to match ProjectInvitation model schema.
        """
        with transaction.atomic():
            invitation, created = ProjectInvitation.objects.get_or_create(
                project=project,
                invitee=invitee,
                defaults={"invited_by": invited_by, "is_admin": is_admin},
            )

            if not created:
                raise ValidationError("Invitation already exists for this user.")

            invite_url = f"{settings.CLIENT_URL}/accept-invite/{invitation.token}"

            transaction.on_commit(
                lambda: send_invitation_email.delay(
                    invitee.email, project.title, invite_url
                )
            )
        return invitation

    @staticmethod
    def accept_invitation(token, request_user):
        """
        Accepts invite: syncs with Jira first, then performs DB operations inside a transaction.
        """
        try:
            invitation = ProjectInvitation.objects.get(token=token)
        except ProjectInvitation.DoesNotExist:
            raise ValidationError("Invalid token")

        if invitation.invitee != request_user:
            raise PermissionDenied("This invitation is not for you.")

        if not invitation.is_valid:
            raise ValidationError("Expired or invalid invitation.")

        JiraProjectService.add_user_to_jira_project(
            user=invitation.invited_by,
            project=invitation.project,
            invitee=invitation.invitee,
            is_admin=invitation.is_admin,
        )

        with transaction.atomic():
            ProjectMember.objects.update_or_create(
                project=invitation.project,
                user=invitation.invitee,
                defaults={
                    "is_admin": invitation.is_admin,
                    "status": MemberStatus.MEMBER,
                },
            )
            invitation.delete()

        return invitation.project

    @staticmethod
    def update_member_role(project, requester, target_user_id, new_role):
        target_member = get_object_or_404(
            ProjectMember, project=project, user_id=target_user_id
        )

        JiraProjectService.update_user_role_in_jira(
            user=requester,
            project=project,
            target_user=target_member.user,
            new_role=new_role,
        )

        with transaction.atomic():
            if new_role == "owner":
                ProjectMember.objects.filter(project=project, user=requester).update(
                    is_admin=True
                )
                project.owner = target_member.user
                project.save()
                target_member.is_admin = True
            else:
                target_member.is_admin = new_role == "admin"
            target_member.save()

    @staticmethod
    def remove_member(project, requester, target_user_id):
        target_member = get_object_or_404(
            ProjectMember, project=project, user_id=target_user_id
        )
        if str(requester.user_id) == str(target_user_id) and project.owner == requester:
            raise ValidationError("Owner cannot leave without transferring ownership.")

        JiraProjectService.remove_user_from_jira_project(
            user=requester, project=project, target_user=target_member.user
        )
        target_member.status = MemberStatus.LEFT
        target_member.save()

    @staticmethod
    def reject_invitation(token, request_user):
        invitation = ProjectInvitation.objects.filter(
            token=token, invitee=request_user, is_accepted=False
        ).first()
        if not invitation:
            raise ValidationError("Invitation not found.")
        invitation.delete()

    @staticmethod
    def get_annotated_members(project_id, requesting_user):
        return (
            ProjectMember.objects.filter(
                project_id=project_id, status=MemberStatus.MEMBER
            )
            .select_related("user")
            .annotate(
                priority=Case(
                    When(user=requesting_user, then=Value(1)),
                    When(user_id=F("project__owner_id"), then=Value(2)),
                    When(is_admin=True, then=Value(3)),
                    default=Value(4),
                    output_field=IntegerField(),
                )
            )
            .order_by("priority", "user__email")
        )

    @staticmethod
    def get_all_users_with_membership_flag(project_id, search_query=None):
        member_subquery = ProjectMember.objects.filter(
            user_id=OuterRef("pk"), project_id=project_id, status=MemberStatus.MEMBER
        )
        queryset = CustomUser.objects.annotate(
            is_project_member=Exists(member_subquery)
        ).order_by("first_name")
        if search_query:
            queryset = queryset.annotate(
                full_name=Concat(
                    "first_name", Value(" "), "last_name", output_field=CharField()
                )
            ).filter(
                Q(full_name__icontains=search_query) | Q(email__icontains=search_query)
            )
        return queryset
