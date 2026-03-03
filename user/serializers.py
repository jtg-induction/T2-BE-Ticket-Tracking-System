from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.utils import encrypt_token

from .models import CustomUser
from .utils import verify_signup_jwt


class UserSerializer(serializers.ModelSerializer):
    """
    User serializer to handle CRUD user.
    """

    password = serializers.CharField(write_only=True, required=True)
    token = serializers.CharField(write_only=True, required=False)

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
        ]
        read_only_fields = ["user_id", "created_at", "email"]

        extra_kwargs = {
            "jira_api_token": {"write_only": True},
        }

    def validate(self, attrs):
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

                if CustomUser.objects.filter(email=email).exists():
                    raise serializers.ValidationError(
                        {"email": "User already exists with this email."}
                    )

                attrs["email"] = email

            except ValueError as e:
                raise serializers.ValidationError({"token": str(e)})
        else:
            attrs.pop("token", None)

        return attrs

    def create(self, validated_data):
        return CustomUser.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
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
        token = super().get_token(user)
        token["jira_id"] = user.jira_id
        return token

    def validate(self, attrs):
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
    Serializer to handle signup email
    """

    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.lower()
        if CustomUser.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email
