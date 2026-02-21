from django.db import transaction
from rest_framework import serializers

from core.services import JiraProjectService
from user.serializers import UserSerializer

from .models import CommentModel


class CommentSerializer(serializers.ModelSerializer):
    """
    Serializer for CommentModel with real-time Jira synchronization.

    Handles the validation and transformation of comment data while ensuring
    that local database state remains consistent with the external Jira issue.
    """

    commentator_id = serializers.ReadOnlyField(source="commentator.id")
    project_name = serializers.CharField(source="ticket.project.name", read_only=True)

    is_project_archived = serializers.BooleanField(
        source="ticket.project.is_archived", read_only=True
    )

    can_edit = serializers.SerializerMethodField()

    message = serializers.CharField(
        max_length=1000,
        error_messages={
            "max_length": "Comment is too long. Please keep it under 10,000 characters."
        },
    )

    class Meta:
        model = CommentModel
        fields = [
            "id",
            "message",
            "commentator_id",
            "project_name",
            "can_edit",
            "is_project_archived",
            "created_at",
            "ticket",
            "external_author_name",
            "commentator",
        ]
        read_only_fields = [
            "id",
            "commentator_id",
            "ticket",
            "created_at",
            "is_project_archived",
        ]

    def get_can_edit(self, obj):
        """
        Check if the user is authorized to edit the comment.

        Returns True if the user is the author and the project is active.
        """
        user = self.context["request"].user
        is_author = obj.commentator == user
        project_archived = obj.ticket.project.is_archived
        return is_author and not project_archived

    def to_representation(self, instance):
        """
        Customizes the output to include the full User object
        instead of just the user_id.
        """
        representation = super().to_representation(instance)

        if instance.commentator:
            representation["commentator"] = UserSerializer(instance.commentator).data
        else:
            representation["commentator"] = None

        return representation

    def create(self, validated_data):
        """
        Create a local comment record and synchronize it with Jira.

        Uses an atomic transaction to ensure that if the Jira API call fails,
        the local database record is not created.
        """
        user = self.context["request"].user
        ticket = validated_data.get("ticket")
        message = validated_data.get("message")

        with transaction.atomic():
            instance = super().create(validated_data)
            try:
                jira_id = JiraProjectService.add_comment_to_jira(
                    user=user, ticket_instance=ticket, message=message
                )

                if not jira_id:
                    raise Exception("Jira API returned no ID.")

            except Exception as e:
                raise serializers.ValidationError(
                    {"detail": f"Jira Sync Failed: {str(e)}"}
                )

            instance.jira_id = jira_id
            instance.save()

            return instance

    def update(self, instance, validated_data):
        """
        Update an existing comment and sync the new message to Jira.

        If the Jira update fails, the local database changes are rolled back
        to prevent a state mismatch between systems.
        """
        user = self.context["request"].user
        new_message = validated_data.get("message", instance.message)

        with transaction.atomic():
            if instance.jira_id:
                instance = super().update(instance, validated_data)
                try:
                    success = JiraProjectService.update_jira_comment(
                        user=user,
                        ticket_instance=instance.ticket,
                        jira_comment_id=instance.jira_id,
                        message=new_message,
                    )
                    if not success:
                        raise Exception("Jira rejected the update.")
                except Exception as e:
                    raise serializers.ValidationError(
                        {"detail": f"Failed to update Jira: {str(e)}"}
                    )

                return instance
