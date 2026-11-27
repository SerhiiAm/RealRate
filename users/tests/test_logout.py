from datetime import timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import RefreshTokenRevocation, User
from users.tests.errors import error, invalid_input

Reason = RefreshTokenRevocation.Reason
PASSWORD = "Str0ng-pass!"
URL = reverse("users:logout")
REFRESH_URL = reverse("users:refresh")
INVALID = error("invalid_refresh_token", "Refresh-токен недійсний або прострочений")

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user("ivan@mail.com", PASSWORD)


def new_refresh(user):
    return str(RefreshToken.for_user(user))


def reason_of(raw_token):
    jti = RefreshToken(raw_token, verify=False)["jti"]
    revocation = RefreshTokenRevocation.objects.filter(token__jti=jti).first()
    return revocation.reason if revocation else None


def logout(client, raw_token):
    return client.post(URL, {"refresh": raw_token}, format="json")


def test_logout_revokes_only_this_session(api_client, user):
    laptop = new_refresh(user)
    phone = new_refresh(user)

    response = logout(api_client, laptop)

    assert response.status_code == 204
    assert response.content == b""
    assert reason_of(laptop) == Reason.LOGOUT
    assert reason_of(phone) is None


def test_refresh_after_logout_fails_but_other_sessions_stay(api_client, user):
    laptop = new_refresh(user)
    phone = new_refresh(user)
    logout(api_client, laptop)

    response = api_client.post(REFRESH_URL, {"refresh": laptop}, format="json")

    assert response.status_code == 401
    assert reason_of(phone) is None  # an old tab is not a theft
    assert (
        api_client.post(REFRESH_URL, {"refresh": phone}, format="json").status_code
        == 200
    )


def test_logout_twice_is_ok(api_client, user):
    raw = new_refresh(user)
    logout(api_client, raw)

    response = logout(api_client, raw)  # double click / retry

    assert response.status_code == 204
    assert reason_of(raw) == Reason.LOGOUT


def test_logout_with_already_exchanged_token_is_not_a_theft(api_client, user):
    old = new_refresh(user)
    new = api_client.post(REFRESH_URL, {"refresh": old}, format="json").json()[
        "refresh"
    ]

    response = logout(api_client, old)

    assert response.status_code == 204
    assert reason_of(old) == Reason.ROTATED  # unchanged
    assert reason_of(new) is None  # the session is still alive


def test_logout_needs_no_access_token(api_client, user):
    # The access token may already be expired when the user clicks "Log out"
    api_client.credentials(HTTP_AUTHORIZATION="Bearer broken.token")

    assert logout(api_client, new_refresh(user)).status_code == 204


def expired_refresh(user):
    token = RefreshToken.for_user(user)
    token.set_exp(lifetime=-timedelta(seconds=1))
    return str(token)


@pytest.mark.parametrize(
    "make_token",
    [
        lambda user: "not-a-token",
        expired_refresh,
        lambda user: str(RefreshToken.for_user(user).access_token),
    ],
    ids=["garbage", "expired", "access-instead-of-refresh"],
)
def test_logout_rejects_bad_tokens(api_client, user, make_token):
    response = logout(api_client, make_token(user))

    assert response.status_code == 401
    assert response.json() == INVALID
    assert not RefreshTokenRevocation.objects.exists()


@pytest.mark.parametrize("data", [{}, {"refresh": ""}])
def test_logout_requires_token(api_client, data):
    response = api_client.post(URL, data, format="json")

    assert response.status_code == 400
    assert response.json() == invalid_input(
        {"refresh": [("required", "Потрібен refresh-токен")]}
    )
