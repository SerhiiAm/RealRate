"""One error format for the whole API.

Any error:          {"code": "invalid_credentials", "message": "..."}
Field errors (400): {"code": "validation_error", "message": "Invalid input",
                     "fields": {"email": [{"code": "email_taken", "message": "..."}]}}

The frontend checks `code` (stable); `message` is text for people.
500 errors are not handled here: Django logs them and answers itself.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler

INVALID_INPUT_MESSAGE = _("Invalid input")

# Our texts for these codes: simplejwt has no Ukrainian translation
# (its texts would stay English), DRF's Ukrainian "throttled" is half English
# and "not_authenticated" is clumsy
MESSAGES = {
    "token_not_valid": _("Token is invalid or expired"),
    "user_inactive": _("User is inactive"),
    "user_not_found": _("User not found"),
    "bad_authorization_header": _(
        "Authorization header must contain two space-delimited values"
    ),
    "not_authenticated": _("Authentication credentials were not provided"),
    "throttled": _("Too many requests, try again later"),
}

# DRF has three codes for "the field is not filled in"; for the frontend
# it is one situation, and our messages are already the same
REQUIRED_CODES = {"blank": "required", "null": "required"}


def _error(detail):
    code = REQUIRED_CODES.get(detail.code, detail.code)
    return {"code": code, "message": str(detail)}


def _field_errors(detail):
    """{"email": ["..."]} -> {"email": [{"code": ..., "message": ...}]}."""
    if isinstance(detail, dict):
        return {field: _field_errors(value) for field, value in detail.items()}
    if isinstance(detail, list):
        return [_field_errors(item) for item in detail]
    return _error(detail)


def _single_error(exc):
    detail = exc.detail
    if isinstance(detail, dict):
        # simplejwt's invalid token: {"detail": "...", "messages": [...]};
        # its "messages" list is not useful for the frontend
        error = {
            "code": str(detail.get("code", exc.default_code)),
            "message": str(detail.get("detail", exc.default_detail)),
        }
    else:
        error = _error(detail)
    if error["code"] in MESSAGES:
        error["message"] = str(MESSAGES[error["code"]])
    return error


def api_exception_handler(exc, context):
    # Same conversion DRF does, but without Django's message
    # ("No User matches the given query.")
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        if not isinstance(detail, dict):
            detail = {api_settings.NON_FIELD_ERRORS_KEY: detail}
        response.data = {
            "code": "validation_error",
            "message": str(INVALID_INPUT_MESSAGE),
            "fields": _field_errors(detail),
        }
    else:
        response.data = _single_error(exc)
    return response
