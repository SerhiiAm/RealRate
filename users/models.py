from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from .validators import validate_email_domain


class Role(models.TextChoices):
    USER = "user", _("User")
    ADMIN = "admin", _("Admin")


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """Lowercase the whole email (Django lowercases only the domain).

        Also used by User.clean(), so admin forms store emails the same way.
        """
        return super().normalize_email(email).lower()

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_("The Email field must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        # is_staff / is_superuser are set by User.save() from role.
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)

        if extra_fields.get("role") != Role.ADMIN:
            raise ValueError(_("Superuser must have role=admin."))

        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email):
        """Find a user by email ignoring case (used by login and createsuperuser)."""
        return self.get(email__iexact=email)


class User(AbstractUser):
    username = None
    # On the model field, so admin forms and createsuperuser check it too
    email = models.EmailField(
        _("email address"), unique=True, validators=[validate_email_domain]
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="user_email_case_insensitive_unique",
                violation_error_message=_("A user with this email already exists."),
            ),
            # Safety net for QuerySet.update() / bulk_create(), which skip save()
            models.CheckConstraint(
                condition=(
                    Q(role=Role.ADMIN, is_staff=True, is_superuser=True)
                    | (~Q(role=Role.ADMIN) & Q(is_staff=False, is_superuser=False))
                ),
                name="user_role_matches_admin_flags",
                violation_error_message=_(
                    "is_staff and is_superuser must match the role."
                ),
            ),
        ]

    def _sync_flags_with_role(self):
        """role is the single source of truth: admin -> both True, else both False."""
        is_admin = self.role == Role.ADMIN
        self.is_staff = is_admin
        self.is_superuser = is_admin

    def clean(self):
        # full_clean() checks constraints, so flags must be synced before it
        super().clean()
        self._sync_flags_with_role()

    def save(self, *args, **kwargs):
        self._sync_flags_with_role()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "role" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"is_staff", "is_superuser"}

        super().save(*args, **kwargs)


class RefreshTokenRevocation(models.Model):
    """Why a refresh token was revoked (simplejwt's blacklist stores no reason).

    Needed to tell theft from a normal logout: sending a token again after it
    was ROTATED means someone else has it; after LOGOUT it is just an old tab.
    """

    class Reason(models.TextChoices):
        ROTATED = "rotated", _("Exchanged for a new pair")
        LOGOUT = "logout", _("Logged out")
        REUSE_DETECTED = "reuse_detected", _("Revoked after reuse was detected")

    token = models.OneToOneField(
        OutstandingToken, on_delete=models.CASCADE, related_name="revocation"
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    revoked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.token.jti}: {self.reason}"
