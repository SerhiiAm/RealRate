from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for the custom User model: email instead of username.

    Access is controlled only by role: is_staff / is_superuser are set by
    User.save(), so they are not editable here.
    """

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (_("Permissions"), {"fields": ("is_active", "role")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "role"),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        """An admin can't change their own role or active status.

        Otherwise one click locks them out of the admin panel.
        """
        readonly = super().get_readonly_fields(request, obj)
        if obj is not None and obj.pk == request.user.pk:
            return (*readonly, "role", "is_active")
        return readonly

    list_display = ("email", "first_name", "last_name", "role")
    list_filter = ("role", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
