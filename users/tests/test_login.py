import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken

from users.models import User
from users.tests.errors import error, invalid_input

PASSWORD = "Str0ng-pass!"
URL = reverse("users:login")
INVALID = error("invalid_credentials", "Неправильний email або пароль")
EMAIL_REQUIRED = ("required", "Вкажіть email")
PASSWORD_REQUIRED = ("required", "Вкажіть пароль")

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    # The login limit is stored in the cache: start every test with zero tries
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user(
        "ivan@mail.com", PASSWORD, first_name="Іван", last_name="Шевченко"
    )


def test_login_returns_user_and_tokens(api_client, user):
    response = api_client.post(
        URL, {"email": "ivan@mail.com", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": user.id,
        "email": "ivan@mail.com",
        "first_name": "Іван",
        "last_name": "Шевченко",
        "role": "user",
    }
    assert set(body) == {"user", "access", "refresh"}
    assert str(AccessToken(body["access"])["user_id"]) == str(user.id)
    assert OutstandingToken.objects.filter(user=user).count() == 1


def test_login_sets_last_login(api_client, user):
    assert user.last_login is None

    api_client.post(
        URL, {"email": "ivan@mail.com", "password": PASSWORD}, format="json"
    )

    user.refresh_from_db()
    assert user.last_login is not None


def test_login_ignores_email_case_and_spaces(api_client, user):
    response = api_client.post(
        URL, {"email": "  IVAN@Mail.com ", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200


def test_login_upgrades_old_password_hash_to_argon2(api_client, user):
    # Users created before Argon2 have PBKDF2 hashes: upgraded on next login
    user.password = make_password(PASSWORD, hasher="pbkdf2_sha256")
    user.save()

    api_client.post(
        URL, {"email": "ivan@mail.com", "password": PASSWORD}, format="json"
    )

    user.refresh_from_db()
    assert user.password.startswith("argon2$")


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("ivan@mail.com", "Wrong-pass1!"),  # wrong password
        ("nobody@mail.com", PASSWORD),  # unknown email
        ("ivan@mail.com", PASSWORD + " "),  # password is not trimmed
        ("not-an-email", PASSWORD),
    ],
)
def test_login_rejects_bad_credentials_with_one_message(
    api_client, user, email, password
):
    response = api_client.post(
        URL, {"email": email, "password": password}, format="json"
    )

    assert response.status_code == 401
    assert response.json() == INVALID
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="api"'
    assert not OutstandingToken.objects.exists()


def test_login_rejects_inactive_user_with_same_message(api_client, user):
    user.is_active = False
    user.save()

    response = api_client.post(
        URL, {"email": "ivan@mail.com", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 401
    assert response.json() == INVALID


@pytest.mark.parametrize(
    ("data", "errors"),
    [
        ({"password": PASSWORD}, {"email": [EMAIL_REQUIRED]}),
        ({"email": " ", "password": PASSWORD}, {"email": [EMAIL_REQUIRED]}),
        ({"email": "ivan@mail.com"}, {"password": [PASSWORD_REQUIRED]}),
        ({"email": "ivan@mail.com", "password": ""}, {"password": [PASSWORD_REQUIRED]}),
        ({}, {"email": [EMAIL_REQUIRED], "password": [PASSWORD_REQUIRED]}),
    ],
)
def test_login_requires_fields(api_client, data, errors):
    response = api_client.post(URL, data, format="json")

    assert response.status_code == 400
    assert response.json() == invalid_input(errors)


def test_login_works_with_broken_auth_header(api_client, user):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer broken.token")

    response = api_client.post(
        URL, {"email": "ivan@mail.com", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200


def test_login_is_limited_to_10_tries_per_minute(api_client, user):
    data = {"email": "ivan@mail.com", "password": "Wrong-pass1!"}
    for _ in range(10):
        assert api_client.post(URL, data, format="json").status_code == 401

    response = api_client.post(URL, data, format="json")

    assert response.status_code == 429
    # Even the right password is blocked until the limit resets
    data["password"] = PASSWORD
    assert api_client.post(URL, data, format="json").status_code == 429


def test_login_limit_cannot_be_bypassed_with_fake_forwarded_ip(api_client, user):
    # By default X-Forwarded-For is not trusted (DJANGO_NUM_PROXIES=0)
    data = {"email": "ivan@mail.com", "password": "Wrong-pass1!"}
    for i in range(10):
        api_client.post(URL, data, format="json", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}")

    response = api_client.post(
        URL, data, format="json", HTTP_X_FORWARDED_FOR="10.0.0.99"
    )

    assert response.status_code == 429
