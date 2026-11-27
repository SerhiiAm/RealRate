"""Refresh token rotation and revocation with reuse (theft) detection.

simplejwt's own refresh view checks the blacklist and blacklists the token in
two separate steps, so two concurrent requests with the same token both get a
new pair. Here every change of a user's tokens first locks the user's row:
operations on one user's tokens run one after another, and since the lock is
always the same (the user row), they can't deadlock.
"""

from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from .models import RefreshTokenRevocation, User

Reason = RefreshTokenRevocation.Reason

INVALID_REFRESH_MESSAGE = "Invalid or expired refresh token"


def _invalid_refresh():
    return AuthenticationFailed(INVALID_REFRESH_MESSAGE, code="invalid_refresh_token")


class _RefreshTokenNoBlacklistCheck(RefreshToken):
    """Checks signature, expiry and type, but not the blacklist.

    The stock check would reject a revoked token before we can tell
    whether it is a theft; we check revocation ourselves under a lock.
    """

    def check_blacklist(self):
        pass


def _decode(raw_token):
    try:
        return _RefreshTokenNoBlacklistCheck(raw_token)
    except TokenError:
        raise _invalid_refresh() from None


def _get_outstanding(token):
    try:
        outstanding = OutstandingToken.objects.get(jti=token["jti"])
    except OutstandingToken.DoesNotExist:
        raise _invalid_refresh() from None
    if outstanding.user_id is None:  # the user was deleted
        raise _invalid_refresh()
    return outstanding


def _lock_user(user_id):
    """Lock the user's row until the transaction ends (call inside atomic)."""
    return User.objects.select_for_update().get(pk=user_id)


def _get_revocation(outstanding):
    # Read AFTER the lock: sees what a concurrent request has just committed
    return RefreshTokenRevocation.objects.filter(token=outstanding).first()


def _revoke(outstanding, reason):
    BlacklistedToken.objects.get_or_create(token=outstanding)
    RefreshTokenRevocation.objects.get_or_create(
        token=outstanding, defaults={"reason": reason}
    )


def _revoke_all_for_user(user_id):
    """Theft: revoke every still active refresh token of the user.

    Bulk inserts: the number of queries doesn't grow with the number of
    sessions. ignore_conflicts skips tokens that already have a row (both
    are one-to-one), like get_or_create in _revoke.
    """
    with transaction.atomic():
        _lock_user(user_id)
        active_ids = list(
            OutstandingToken.objects.filter(
                user_id=user_id, revocation__isnull=True
            ).values_list("pk", flat=True)
        )
        BlacklistedToken.objects.bulk_create(
            [BlacklistedToken(token_id=pk) for pk in active_ids],
            ignore_conflicts=True,
        )
        RefreshTokenRevocation.objects.bulk_create(
            [
                RefreshTokenRevocation(token_id=pk, reason=Reason.REUSE_DETECTED)
                for pk in active_ids
            ],
            ignore_conflicts=True,
        )


def rotate_refresh_token(raw_token):
    """Exchange a refresh token for a new pair; revoke the old one.

    Reuse of a token that was already exchanged means it was stolen:
    all sessions of the user are ended (the thief's and the owner's).
    """
    outstanding = _get_outstanding(_decode(raw_token))

    with transaction.atomic():
        user = _lock_user(outstanding.user_id)
        revocation = _get_revocation(outstanding)

        if revocation is None and user.is_active:
            _revoke(outstanding, Reason.ROTATED)
            new = RefreshToken.for_user(user)
            return {"access": str(new.access_token), "refresh": str(new)}

    if revocation is not None and revocation.reason == Reason.ROTATED:
        # Own transaction, committed even though this request fails
        _revoke_all_for_user(outstanding.user_id)
    # LOGOUT / REUSE_DETECTED: an old tab or a retry, not a theft
    raise _invalid_refresh()


def revoke_refresh_token(raw_token):
    """Logout: revoke this refresh token only; other sessions stay.

    Idempotent: an already revoked token (double click, retry, a token that
    was already exchanged) is left as is and is NOT treated as a theft.
    """
    outstanding = _get_outstanding(_decode(raw_token))

    with transaction.atomic():
        _lock_user(outstanding.user_id)
        if _get_revocation(outstanding) is None:
            _revoke(outstanding, Reason.LOGOUT)
