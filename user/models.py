import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models

from core.models import BaseModel, SoftDeleteManager
from core.utils import decrypt_token, encrypt_token

from .enums import Roles


class UserManager(BaseUserManager, SoftDeleteManager):
    """
    Unified manager for User creation and Soft Delete filtering.
    """

    def create_user(
        self, email, jira_id, jira_api_token, password=None, **extra_fields
    ):

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            jira_id=jira_id,
            jira_api_token=encrypt_token(jira_api_token),
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email, jira_id, jira_api_token, password=None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(
            email, jira_id, jira_api_token, password, **extra_fields
        )


class CustomUser(AbstractBaseUser, PermissionsMixin, BaseModel):
    """
    Custom user model inheriting from BaseModel.
    """

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jira_id = models.TextField(unique=True, max_length=43)
    jira_api_token = models.TextField(max_length=256)
    email = models.EmailField(unique=True)
    first_name = models.TextField(max_length=50)
    last_name = models.TextField(max_length=50, blank=True)
    about = models.TextField(max_length=500, blank=True)
    role = models.TextField(
        choices=Roles.choices, max_length=3, default=Roles.software_dev
    )
    dob = models.DateTimeField(null=True, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["jira_id", "first_name", "jira_api_token"]

    objects = UserManager()

    def get_decrypted_jira_token(self):
        return decrypt_token(self.jira_api_token)

    def __str__(self):
        return self.email
