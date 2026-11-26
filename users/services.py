"""Business logic of registration and login (views only accept and answer).

Refresh and logout live in tokens.py.
"""

from django.contrib.auth.models import update_last_login
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import EMAIL_TAKEN_MESSAGE


def log_in(user):
    """Set last_login and issue a new token pair (recorded for blacklisting)."""
    with transaction.atomic():
        update_last_login(None, user)
        refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _create_user(email, first_name, last_name, password):
    try:
        # Savepoint: a failed INSERT must not break the outer transaction
        with transaction.atomic():
            return User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
    except IntegrityError:
        # Race: the same email was registered between validation and INSERT
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                {"email": [EMAIL_TAKEN_MESSAGE]}
            ) from None
        raise


def register(*, email, first_name, last_name, password):
    """Create the user and log them in at once.

    One transaction: if tokens fail, the user is not left half-registered.
    Registration counts as the first login (last_login is set, for analytics).
    """
    with transaction.atomic():
        user = _create_user(email, first_name, last_name, password)
        tokens = log_in(user)
    return user, tokens
