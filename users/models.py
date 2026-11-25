from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


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
    email = models.EmailField(_("email address"), unique=True)
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
        ]

    def save(self, *args, **kwargs):
        """Keep is_staff and is_superuser in sync with role.

        role is the single source of truth: admin -> both True, user -> both False.
        QuerySet.update() and bulk_create() bypass this method - don't use them
        to change role.
        """
        is_admin = self.role == Role.ADMIN
        self.is_staff = is_admin
        self.is_superuser = is_admin

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "role" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"is_staff", "is_superuser"}

        super().save(*args, **kwargs)
