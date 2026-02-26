import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from safedelete.models import SafeDeleteModel
from safedelete.managers import SafeDeleteManager

from .enums import Roles
from .utils import encrypt_token, decrypt_token


class UserManager(BaseUserManager, SafeDeleteManager):
    """
    Custom manager for handling user creation.
    """

    def create_user(self, email, jira_id, jira_api_token, password=None, **extra_fields):
        """
        Create regular user with given email and password.
        """
        if not email:
            raise ValueError("Email is required")
        
        if not jira_id:
            raise ValueError("JIRA ID is required")
        
        if not extra_fields.get('first_name'):
            raise ValueError("The First Name field must be set")
        
        if not jira_api_token:
            raise ValueError("JIRA API Token is required")

        try:
            validate_email(email)
        except ValidationError:
            raise ValueError("You must have provided a valid email address") from None

        if not password:
            raise ValueError("Password is required")

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            jira_id=jira_id,
            # Encrypt right here at the manager level
            jira_api_token=encrypt_token(jira_api_token), 
            **extra_fields
        )
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email,jira_id, jira_api_token, password=None, **extra_fields):
        """
        Create superuser with admin privileges.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff = True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser = True")

        return self.create_user(email, jira_id, jira_api_token, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin, SafeDeleteModel):
    """
    Custom user model.
    """

    user_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
    )
    jira_id = models.TextField(unique=True, max_length=43)
    jira_api_token= models.TextField(unique=True,max_length=256)
    email = models.EmailField(unique=True)
    first_name = models.TextField(max_length=50)
    last_name = models.TextField(max_length=50,blank=True)
    about = models.TextField(max_length=500, blank=True)
    role = models.TextField(
        choices=Roles.choices,
        max_length=3,
        default=Roles.software_dev
    )
    dob = models.DateTimeField(null=True, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ['jira_id', 'first_name', 'jira_api_token']

    objects = UserManager()

    def get_decrypted_jira_token(self):
        """
        Helper to retrieve the usable plaintext token.
        """
        return decrypt_token(self.jira_api_token)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        
    def __str__(self):
        return self.email
