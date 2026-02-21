from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.utils import encrypt_token

from .models import CustomUser
from .utils import verify_signup_jwt


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for handling User CRUD operations and registration.

    Manages user data including sensitive Jira credentials
    and handles the logic for token-based registration via `verify_signup_jwt`.
    """

    can_edit = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=True)
    token = serializers.CharField(write_only=True, required=False)
    email = serializers.EmailField(required=False)

    class Meta:
        model = CustomUser
        fields = [
            "user_id",
            "email",
            "token",
            "jira_id",
            "jira_api_token",
            "first_name",
            "last_name",
            "about",
            "role",
            "dob",
            "password",
            "created_at",
            "can_edit",
        ]
        read_only_fields = ["user_id", "created_at"]

        extra_kwargs = {
            "jira_api_token": {"write_only": True},
        }

    def get_can_edit(self, obj):
        """
        calculates weather current user have permission over the user instance

        Args:
            obj (CustomUser): The user instance being serialized.

        Returns:
            bool: True if the requester is the owner of the account, False otherwise.

        """
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.user_id == request.user.user_id
        return False

    def validate(self, attrs):
        """
        Validates the registration token or update data.

        Args:
            attrs (dict): The dictionary of input data.

        Returns:
            dict: The validated data with the verified email injected if registering.
        """

        if self.instance is None:
            token = attrs.pop("token", None)
            if not token:
                raise serializers.ValidationError(
                    {"token": "Token is required for registration."}
                )

            try:
                email = verify_signup_jwt(token)
                if not email:
                    raise serializers.ValidationError(
                        {
                            "token": "The provided token is invalid or missing the email claim."
                        }
                    )

                if CustomUser.all_objects.filter(email=email).exists():
                    raise serializers.ValidationError(
                        {"email": "User already exists with this email."}
                    )

                attrs["email"] = email

            except ValueError as e:
                raise serializers.ValidationError({"token": str(e)})
        else:
            attrs.pop("token", None)

            if "email" in attrs:
                raise serializers.ValidationError(
                    {"email": "This field cannot be modified."}
                )

            if "jira_id" in attrs:
                raise serializers.ValidationError(
                    {"jira_id": "This field cannot be modified."}
                )

        return attrs

    def create(self, validated_data):
        """
        Creates a new CustomUser instance using the UserManager.

        Args:
            validated_data (dict): Validated data from the serializer.

        Returns:
            CustomUser: The created user instance.
        """
        return CustomUser.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        """
        Updates an existing CustomUser instance.

        Args:
            instance (CustomUser): The user instance to update.
            validated_data (dict): The new data to apply.

        Returns:
            CustomUser: The updated user instance.
        """
        password = validated_data.pop("password", None)
        validated_data.pop("jira_id", None)
        if password:
            instance.set_password(password)

        jira_token = validated_data.pop("jira_api_token", None)
        if jira_token:
            instance.jira_api_token = encrypt_token(jira_token)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer to handle generation of access and refresh token
    """

    @classmethod
    def get_token(cls, user):
        """
        Extends the standard token with custom claims.

        Args:
            user (CustomUser): The user instance for which the token is generated.

        Returns:
            Token: The JWT token object with added claims.
        """
        token = super().get_token(user)
        token["jira_id"] = user.jira_id
        return token

    def validate(self, attrs):
        """
        Extends the validation response data with user profile information.

        Args:
            attrs (dict): User credentials (email and password).

        Returns:
            dict: The standard response data (access/refresh) plus a 'user' object.
        """

        data = super().validate(attrs)
        data["user"] = {
            "user_id": self.user.user_id,
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "role": self.user.role,
            "about": self.user.about,
            "dob": self.user.dob,
            "jira_id": self.user.jira_id,
        }
        return data


class SignupLinkRequestSerializer(serializers.Serializer):
    """
    Serializer to validate requests for sending a signup email.
    """

    email = serializers.EmailField()

    def validate_email(self, value):
        """
        Checks for existing accounts.

        Args:
            value (str): The raw email string.

        Returns:
            str: The email string.
        """
        email = value.lower()
        if CustomUser.all_objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email
