import unicodedata

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from users.models import Role, User
from users.serializers import RegisterSerializer
from users.tests.errors import invalid_input

PASSWORD = "Str0ng-pass!"
URL = reverse("users:register")

FIRST_NAME_MESSAGE = (
    "Name must be 2–20 characters, start with a letter and contain only "
    "letters, hyphens, or apostrophes"
)
LAST_NAME_MESSAGE = (
    "Last name must be 2–20 characters, start with a letter and contain only "
    "letters, hyphens, or apostrophes"
)
PASSWORD_MESSAGE = (
    "Password must be 8–64 characters, include at least 1 uppercase letter, "
    "1 number, 1 special character, and no spaces"
)
# (code, message) pairs of field errors
FIRST_NAME_INVALID = ("invalid", FIRST_NAME_MESSAGE)
LAST_NAME_INVALID = ("invalid", LAST_NAME_MESSAGE)
PASSWORD_INVALID = ("password_invalid", PASSWORD_MESSAGE)
EMAIL_REQUIRED = ("required", "Email is required")
EMAIL_INVALID = ("invalid", "Please enter a valid email address")
EMAIL_TAKEN = invalid_input(
    {"email": [("email_taken", "This email is already registered")]}
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


def payload(**changes):
    """Valid registration data; a value of ... removes the field."""
    data = {
        "email": "ivan@mail.com",
        "first_name": "Іван",
        "last_name": "Шевченко",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        **changes,
    }
    return {key: value for key, value in data.items() if value is not ...}


def test_register_creates_user_and_returns_tokens(api_client):
    response = api_client.post(URL, payload(), format="json")

    assert response.status_code == 201
    user = User.objects.get()
    body = response.json()
    assert body["user"] == {
        "id": user.id,
        "email": "ivan@mail.com",
        "first_name": "Іван",
        "last_name": "Шевченко",
        "role": "user",
    }
    assert set(body) == {"user", "access", "refresh"}
    access = AccessToken(body["access"])
    refresh = RefreshToken(body["refresh"])
    assert str(access["user_id"]) == str(user.id)
    # Both tokens count from the refresh token's creation time; access "iat"
    # is set a moment later and can fall into the next second
    assert access["exp"] - refresh["iat"] == 15 * 60
    assert refresh["exp"] - refresh["iat"] == 3 * 24 * 60 * 60
    assert OutstandingToken.objects.filter(user=user).count() == 1  # for blacklist


def test_register_stores_regular_user_with_argon2_and_last_login(api_client):
    api_client.post(URL, payload(), format="json")

    user = User.objects.get()
    assert user.role == Role.USER
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.password.startswith("argon2$")
    assert user.check_password(PASSWORD)
    assert user.last_login is not None  # analytics: registration = first login


def test_register_ignores_role_and_admin_flags(api_client):
    data = payload(role="admin", is_staff=True, is_superuser=True, id=999)

    response = api_client.post(URL, data, format="json")

    assert response.status_code == 201
    user = User.objects.get()
    assert user.role == Role.USER
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.id != 999
    assert response.json()["user"]["role"] == "user"


def test_register_works_with_broken_auth_header(api_client):
    # An old token left in the frontend must not turn registration into 401
    api_client.credentials(HTTP_AUTHORIZATION="Bearer broken.token")

    response = api_client.post(URL, payload(), format="json")

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("changes", "field", "stored"),
    [
        ({"email": "  Ivan@Mail.COM "}, "email", "ivan@mail.com"),
        ({"email": "a" * 245 + "@mail.com"}, "email", "a" * 245 + "@mail.com"),
        ({"last_name": ...}, "last_name", ""),
        ({"last_name": ""}, "last_name", ""),
        ({"first_name": "А" * 20}, "first_name", "А" * 20),
        ({"first_name": "Д'Ар’яʼна"}, "first_name", "Д'Ар’яʼна"),
        ({"first_name": "Анна-Марія"}, "first_name", "Анна-Марія"),
        ({"first_name": "John"}, "first_name", "John"),
        # macOS may send "ї" as "і" + combining mark: stored as one letter
        ({"first_name": unicodedata.normalize("NFD", "Їжак")}, "first_name", "Їжак"),
    ],
)
def test_register_accepts_and_normalizes(api_client, changes, field, stored):
    response = api_client.post(URL, payload(**changes), format="json")

    assert response.status_code == 201
    assert getattr(User.objects.get(), field) == stored


@pytest.mark.parametrize(
    ("changes", "errors"),
    [
        # email
        ({"email": ...}, {"email": [EMAIL_REQUIRED]}),
        ({"email": "  "}, {"email": [EMAIL_REQUIRED]}),
        ({"email": None}, {"email": [EMAIL_REQUIRED]}),
        ({"email": "abc"}, {"email": [EMAIL_INVALID]}),
        ({"email": "x@localhost"}, {"email": [EMAIL_INVALID]}),
        (
            {"email": "a" * 246 + "@mail.com"},
            {"email": [("max_length", EMAIL_INVALID[1])]},
        ),
        ({"email": "іван@mail.com"}, {"email": [EMAIL_INVALID]}),
        # first_name
        ({"first_name": ...}, {"first_name": [("required", "Name is required")]}),
        ({"first_name": " "}, {"first_name": [("required", "Name is required")]}),
        ({"first_name": "І"}, {"first_name": [FIRST_NAME_INVALID]}),
        ({"first_name": "А" * 21}, {"first_name": [FIRST_NAME_INVALID]}),
        ({"first_name": "-Іван"}, {"first_name": [FIRST_NAME_INVALID]}),
        ({"first_name": "Анна Марія"}, {"first_name": [FIRST_NAME_INVALID]}),
        ({"first_name": "Іван2"}, {"first_name": [FIRST_NAME_INVALID]}),
        ({"first_name": "Ыван"}, {"first_name": [FIRST_NAME_INVALID]}),
        # last_name: optional, but checked when given; null is a wrong value,
        # not a missing one (so "invalid", not "required")
        ({"last_name": "К"}, {"last_name": [LAST_NAME_INVALID]}),
        ({"last_name": None}, {"last_name": [LAST_NAME_INVALID]}),
        # password
        ({"password": ...}, {"password": [("required", "Password is required")]}),
        (
            {"password": "Str0ng pass!", "password_confirm": "Str0ng pass!"},
            {"password": [PASSWORD_INVALID]},
        ),
        (
            {"password": PASSWORD + " ", "password_confirm": PASSWORD + " "},
            {"password": [PASSWORD_INVALID]},  # not trimmed silently
        ),
        (
            {"password": "Password1!", "password_confirm": "Password1!"},
            {"password": [("password_too_common", "This password is too common.")]},
        ),
        (
            {
                "email": "ivanenko@mail.com",
                "password": "Ivanenko1!",
                "password_confirm": "Ivanenko1!",
            },
            {
                "password": [
                    (
                        "password_too_similar",
                        "The password is too similar to the email address.",
                    )
                ]
            },
        ),
        # password_confirm
        (
            {"password_confirm": ...},
            {"password_confirm": [("required", "Please confirm your password")]},
        ),
        (
            {"password_confirm": PASSWORD + "?"},
            {
                "password_confirm": [
                    ("passwords_do_not_match", "Passwords do not match")
                ]
            },
        ),
        # several fields at once: all errors in one response
        (
            {
                "email": "abc",
                "first_name": "І",
                "password": "Str0ng pass!",
                "password_confirm": "Str0ng pass!",
            },
            {
                "email": [EMAIL_INVALID],
                "first_name": [FIRST_NAME_INVALID],
                "password": [PASSWORD_INVALID],
            },
        ),
    ],
)
def test_register_rejects_invalid_data(api_client, changes, errors):
    response = api_client.post(URL, payload(**changes), format="json")

    assert response.status_code == 400
    assert response.json() == invalid_input(errors)
    assert not User.objects.exists()


@pytest.mark.parametrize("field", ["email", "first_name"])
def test_register_rejects_nul_character_with_400(api_client, field):
    # PostgreSQL can't store NUL: without validation this would be 500
    response = api_client.post(URL, payload(**{field: "iv\x00an"}), format="json")

    assert response.status_code == 400
    assert field in response.json()["fields"]


def test_register_rejects_taken_email_in_other_case(api_client):
    User.objects.create_user("ivan@mail.com", PASSWORD)

    response = api_client.post(URL, payload(email="IVAN@Mail.com"), format="json")

    assert response.status_code == 400
    assert response.json() == EMAIL_TAKEN
    assert User.objects.count() == 1


def test_register_leaves_no_user_if_tokens_fail(api_client, monkeypatch):
    def broken_for_user(user):
        raise RuntimeError("token error")

    monkeypatch.setattr(RefreshToken, "for_user", broken_for_user)

    with pytest.raises(RuntimeError):
        api_client.post(URL, payload(), format="json")

    assert not User.objects.exists()


def test_register_race_on_same_email_returns_400(api_client, monkeypatch):
    # Race: another request registered the email after our check passed.
    # Skipping the check lets the INSERT hit the DB unique constraint.
    User.objects.create_user("ivan@mail.com", PASSWORD)
    monkeypatch.setattr(RegisterSerializer, "validate_email", lambda self, v: v.lower())

    response = api_client.post(URL, payload(), format="json")

    assert response.status_code == 400
    assert response.json() == EMAIL_TAKEN
    assert User.objects.count() == 1
