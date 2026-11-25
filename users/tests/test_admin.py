import pytest
from django.contrib.admin.sites import site
from django.urls import reverse

from users.models import Role, User

PASSWORD = "Str0ng-pass!"

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("view", ["add", "change"])
def test_admin_forms_have_role_but_not_flags(rf, admin_user, view):
    model_admin = site._registry[User]
    request = rf.get("/")
    request.user = admin_user
    obj = admin_user if view == "change" else None

    fields = model_admin.get_form(request, obj).base_fields

    assert "role" in fields
    assert "is_staff" not in fields
    assert "is_superuser" not in fields


def test_admin_change_page_opens(admin_client, admin_user):
    url = reverse("admin:users_user_change", args=[admin_user.pk])

    response = admin_client.get(url)

    assert response.status_code == 200


def test_admin_creates_admin_by_role(admin_client):
    response = admin_client.post(
        reverse("admin:users_user_add"),
        {
            "email": "new-admin@mail.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "role": Role.ADMIN,
        },
    )

    assert response.status_code == 302  # redirect = form saved
    user = User.objects.get(email="new-admin@mail.com")
    assert user.is_staff is True
    assert user.is_superuser is True
