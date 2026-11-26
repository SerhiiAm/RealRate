import threading
import time
from datetime import timedelta

import pytest
from django.db import connection
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from users import tokens
from users.models import RefreshTokenRevocation, User
from users.tests.errors import error, invalid_input

Reason = RefreshTokenRevocation.Reason
PASSWORD = "Str0ng-pass!"
URL = reverse("users:refresh")
INVALID = error("invalid_refresh_token", "Invalid or expired refresh token")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user("ivan@mail.com", PASSWORD)


def new_refresh(user):
    """A refresh token as login would issue it (recorded in OutstandingToken)."""
    return str(RefreshToken.for_user(user))


def reason_of(raw_token):
    jti = RefreshToken(raw_token, verify=False)["jti"]
    revocation = RefreshTokenRevocation.objects.filter(token__jti=jti).first()
    return revocation.reason if revocation else None


def post_refresh(client, raw_token):
    return client.post(URL, {"refresh": raw_token}, format="json")


@pytest.mark.django_db
def test_refresh_returns_new_pair_and_revokes_old(api_client, user):
    old = new_refresh(user)

    response = post_refresh(api_client, old)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access", "refresh"}
    assert body["refresh"] != old
    assert str(AccessToken(body["access"])["user_id"]) == str(user.id)
    assert reason_of(old) == Reason.ROTATED
    assert reason_of(body["refresh"]) is None


@pytest.mark.django_db
def test_new_refresh_token_can_be_refreshed_again(api_client, user):
    first = post_refresh(api_client, new_refresh(user)).json()["refresh"]

    response = post_refresh(api_client, first)

    assert response.status_code == 200


@pytest.mark.django_db
def test_reuse_of_rotated_token_ends_all_sessions(api_client, user):
    stolen = new_refresh(user)
    phone = new_refresh(user)  # another device of the same user
    other_user_token = new_refresh(User.objects.create_user("olga@mail.com", PASSWORD))
    owner_new = post_refresh(api_client, stolen).json()["refresh"]

    response = post_refresh(api_client, stolen)  # the thief uses it again

    assert response.status_code == 401
    assert response.json() == INVALID
    assert reason_of(owner_new) == Reason.REUSE_DETECTED
    assert reason_of(phone) == Reason.REUSE_DETECTED
    assert reason_of(stolen) == Reason.ROTATED  # keeps its original reason
    assert reason_of(other_user_token) is None  # other users are not touched
    assert post_refresh(api_client, owner_new).status_code == 401


@pytest.mark.django_db
def test_reuse_after_logout_is_not_a_theft(api_client, user):
    logged_out = new_refresh(user)
    phone = new_refresh(user)
    api_client.post(reverse("users:logout"), {"refresh": logged_out}, format="json")

    response = post_refresh(api_client, logged_out)  # an old tab after logout

    assert response.status_code == 401
    assert reason_of(phone) is None  # other sessions stay
    assert post_refresh(api_client, phone).status_code == 200


@pytest.mark.django_db
def test_revoked_token_is_in_simplejwt_blacklist(api_client, user):
    # So simplejwt's own tools (admin, check_blacklist) also see it as revoked
    old = new_refresh(user)

    post_refresh(api_client, old)

    assert BlacklistedToken.objects.filter(
        token__jti=RefreshToken(old, verify=False)["jti"]
    ).exists()


def expired_refresh(user):
    token = RefreshToken.for_user(user)
    token.set_exp(lifetime=-timedelta(seconds=1))
    return str(token)


def tampered_refresh(user):
    raw = new_refresh(user)
    return raw[:-2] + ("aa" if raw[-2:] != "aa" else "bb")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "make_token",
    [
        lambda user: "not-a-token",
        tampered_refresh,  # wrong signature
        expired_refresh,
        lambda user: str(RefreshToken.for_user(user).access_token),  # wrong type
    ],
    ids=["garbage", "tampered", "expired", "access-instead-of-refresh"],
)
def test_refresh_rejects_bad_tokens(api_client, user, make_token):
    response = post_refresh(api_client, make_token(user))

    assert response.status_code == 401
    assert response.json() == INVALID
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="api"'
    assert not RefreshTokenRevocation.objects.exists()


@pytest.mark.django_db
def test_refresh_rejects_token_unknown_to_database(api_client, user):
    raw = new_refresh(user)
    OutstandingToken.objects.all().delete()

    assert post_refresh(api_client, raw).status_code == 401


@pytest.mark.django_db
def test_refresh_rejects_inactive_user_without_revoking(api_client, user):
    raw = new_refresh(user)
    user.is_active = False
    user.save()

    response = post_refresh(api_client, raw)

    assert response.status_code == 401
    assert reason_of(raw) is None


@pytest.mark.django_db
@pytest.mark.parametrize("data", [{}, {"refresh": ""}, {"refresh": None}])
def test_refresh_requires_token(api_client, data):
    response = api_client.post(URL, data, format="json")

    assert response.status_code == 400
    assert response.json() == invalid_input(
        {"refresh": [("required", "Refresh token is required")]}
    )


@pytest.mark.django_db
def test_refresh_works_with_broken_auth_header(api_client, user):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer broken.token")

    assert post_refresh(api_client, new_refresh(user)).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_refreshes_with_same_token(user, monkeypatch):
    # Real race: two threads, two DB connections. A pause after reading the
    # revocation widens the race window: without the lock both requests
    # would read "not revoked" and both get a new pair.
    original = tokens._get_revocation

    def slow_get_revocation(outstanding):
        result = original(outstanding)
        time.sleep(0.3)
        return result

    monkeypatch.setattr(tokens, "_get_revocation", slow_get_revocation)
    raw = new_refresh(user)
    start = threading.Barrier(2)
    statuses = []

    def worker():
        try:
            start.wait()
            statuses.append(post_refresh(APIClient(), raw).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # One wins, the other is a reuse: it fails and ends all sessions,
    # including the pair the winner has just received
    assert sorted(statuses) == [200, 401]
    assert not OutstandingToken.objects.filter(
        user=user, revocation__isnull=True
    ).exists()
