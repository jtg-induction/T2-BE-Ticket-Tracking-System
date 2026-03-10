from django.conf import settings
from django.db import models


class SafeDeleteQuerySet(models.QuerySet):
    """
    Custom queryset soft delete.
    """

    def delete(self):
        """
        Bulk soft delete implementation.
        """
        for obj in self:
            obj.delete()

        return (len(self), {self.model._meta.label: len(self)})

    def hard_delete(self):
        """
        Permanent bulk record removal.
        """
        return super().delete()


class SoftDeleteManager(models.Manager):
    """
    Manager for active records.
    """

    def __init__(self, show_deleted=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_deleted = show_deleted

    def get_queryset(self):
        """
        Return non-deleted records only.
        """
        qs = SafeDeleteQuerySet(self.model, using=self.db)
        if not self.show_deleted:
            return qs.filter(is_deleted=False)
        return qs


class BaseModel(models.Model):
    """
    Abstract base for all.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_%(class)s_set",
    )
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteManager(show_deleted=True)

    class Meta:
        """
        Define model as abstract.
        """

        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        Toggle soft delete flag.
        """
        self.is_deleted = True
        self.save(update_fields=["is_deleted", "updated_at"], using=using)

        for related_object in self._meta.related_objects:
            if related_object.on_delete == models.CASCADE and issubclass(
                related_object.related_model, BaseModel
            ):
                related_queryset = getattr(
                    self, related_object.get_accessor_name()
                ).all()
                related_queryset.delete()

        return (1, {self._meta.label: 1})

    def hard_delete(self, using=None):
        """
        Perform permanent database deletion.
        """
        return super().delete(using=using)
