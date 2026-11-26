from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import get_error_detail

from .models import User
from .validators import (
    EMAIL_INVALID_MESSAGE,
    normalize_and_validate_name,
    validate_email_domain,
)

FIRST_NAME_MESSAGE = (
    "Name must be 2–20 characters, start with a letter and contain only "
    "letters, hyphens, or apostrophes"
)
LAST_NAME_MESSAGE = (
    "Last name must be 2–20 characters, start with a letter and contain only "
    "letters, hyphens, or apostrophes"
)
EMAIL_TAKEN_MESSAGE = "This email is already registered"
EMAIL_TAKEN_CODE = "email_taken"
# One message for a wrong password, an unknown email and an inactive account:
# otherwise anyone could find out which emails are registered
INVALID_CREDENTIALS_MESSAGE = "Invalid email or password"


def required_messages(message):
    """Same message for a missing field, an empty string and null."""
    return {"required": message, "blank": message, "null": message}


class UserSerializer(serializers.ModelSerializer):
    """User block in responses (register, login, /me)."""

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "role")
        read_only_fields = fields


class AuthResponseSerializer(serializers.Serializer):
    """Response of register and login: user block + JWT pair.

    Used only to describe the response in Swagger.
    """

    user = UserSerializer()
    access = serializers.CharField()
    refresh = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    """Response of refresh. Used only to describe it in Swagger."""

    access = serializers.CharField()
    refresh = serializers.CharField()


class RefreshSerializer(serializers.Serializer):
    """Input of refresh and logout."""

    refresh = serializers.CharField(
        error_messages=required_messages("Refresh token is required")
    )


class LoginSerializer(serializers.Serializer):
    # CharField, not EmailField: a badly formatted email simply doesn't match
    # any account, so it gets the same "Invalid email or password"
    email = serializers.CharField(error_messages=required_messages("Email is required"))
    # Not trimmed, same as in registration
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
        error_messages=required_messages("Password is required"),
    )

    def validate(self, attrs):
        # Django's backend: email lookup ignores case, inactive users are
        # rejected, and a password hash is still computed for unknown emails
        # (so the response time doesn't reveal whether the email exists)
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"],
            password=attrs["password"],
        )
        if user is None:
            raise exceptions.AuthenticationFailed(
                INVALID_CREDENTIALS_MESSAGE, code="invalid_credentials"
            )
        attrs["user"] = user
        return attrs


class RegisterSerializer(serializers.Serializer):
    """Registration input. Only these five fields are accepted:
    anything else (role, is_staff, is_superuser, ...) is ignored.
    """

    # Declared explicitly (not ModelSerializer): no case-sensitive
    # UniqueValidator, our own case-insensitive check in validate_email.
    email = serializers.EmailField(
        max_length=254,
        validators=[validate_email_domain],
        error_messages={
            **required_messages("Email is required"),
            "invalid": EMAIL_INVALID_MESSAGE,
            "max_length": EMAIL_INVALID_MESSAGE,
        },
    )
    first_name = serializers.CharField(
        error_messages=required_messages("Name is required"),
    )
    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        # null is checked in validate_last_name: DRF's "null" code would
        # become "required", which is wrong for an optional field
        allow_null=True,
    )
    # trim_whitespace=False: a space must fail the rules, not be cut silently
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
        error_messages=required_messages("Password is required"),
    )
    password_confirm = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
        error_messages=required_messages("Please confirm your password"),
    )

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                EMAIL_TAKEN_MESSAGE, code=EMAIL_TAKEN_CODE
            )
        return email

    def validate_first_name(self, value):
        return normalize_and_validate_name(value, FIRST_NAME_MESSAGE)

    def validate_last_name(self, value):
        if value is None:
            raise serializers.ValidationError(LAST_NAME_MESSAGE, code="invalid")
        if value == "":
            return value
        return normalize_and_validate_name(value, LAST_NAME_MESSAGE)

    def validate_password(self, value):
        # Rules and "too common" here, so the error is shown together with
        # other fields' errors (validate() runs only when all fields are valid)
        password_validation.validate_password(value)
        return value

    def validate(self, attrs):
        errors = {}

        # Same validators again, now with the user: adds "too similar to email"
        candidate = User(
            email=attrs["email"],
            first_name=attrs["first_name"],
            last_name=attrs["last_name"],
        )
        try:
            password_validation.validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            # Keeps the codes (password_too_similar), not only the texts
            errors["password"] = get_error_detail(exc)

        if attrs["password"] != attrs["password_confirm"]:
            errors["password_confirm"] = [
                ErrorDetail("Passwords do not match", code="passwords_do_not_match")
            ]

        if errors:
            raise serializers.ValidationError(errors)

        # Only needed for the check above; the user is created by services.register
        attrs.pop("password_confirm")
        return attrs
