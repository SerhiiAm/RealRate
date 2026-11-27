import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from users.models import User
from users.tests.errors import error, invalid_input

pytestmark = pytest.mark.django_db


class ProtectedView(APIView):
    """Stands for any endpoint that requires login (like the future /me)."""

    def get(self, request):
        return Response({"ok": True})


class RaisingView(APIView):
    """Raises the exception given in the request, as a real view could."""

    permission_classes = (AllowAny,)
    exception = None

    def get(self, request):
        raise self.exception


def get(view, **headers):
    request = APIRequestFactory().get("/test/", **headers)
    return view.as_view()(request)


def bearer(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}


@pytest.fixture
def user():
    return User.objects.create_user("ivan@mail.com", "Str0ng-pass!")


def test_no_token():
    response = get(ProtectedView)

    assert response.status_code == 401
    assert response.data == error("not_authenticated", "Потрібно увійти в акаунт")


def test_broken_token_gets_short_message():
    response = get(ProtectedView, HTTP_AUTHORIZATION="Bearer broken")

    assert response.status_code == 401
    assert response.data == error("token_not_valid", "Токен недійсний або прострочений")


def test_token_of_inactive_user(user):
    headers = bearer(user)
    user.is_active = False
    user.save()

    response = get(ProtectedView, **headers)

    assert response.status_code == 401
    assert response.data == error("user_inactive", "Акаунт деактивовано")


def test_valid_token_is_not_an_error(user):
    response = get(ProtectedView, **bearer(user))

    assert response.status_code == 200
    assert response.data == {"ok": True}


@pytest.mark.parametrize(
    ("exception", "status_code", "body"),
    [
        (
            Http404("No User matches the given query."),
            404,
            ("not_found", "Не знайдено."),
        ),
        (
            PermissionDenied(),
            403,
            ("permission_denied", "У вас нема дозволу робити цю дію."),
        ),
        # Error not tied to a field
        (
            serializers.ValidationError("Shop is closed", code="shop_closed"),
            400,
            invalid_input({"non_field_errors": [("shop_closed", "Shop is closed")]}),
        ),
    ],
)
def test_other_errors(exception, status_code, body):
    view = type("View", (RaisingView,), {"exception": exception})

    response = get(view)

    assert response.status_code == status_code
    expected = body if isinstance(body, dict) else error(*body)
    assert response.data == expected


def test_server_error_is_left_to_django():
    # Not turned into JSON: Django must log the traceback and answer 500
    view = type("View", (RaisingView,), {"exception": ZeroDivisionError()})

    with pytest.raises(ZeroDivisionError):
        get(view)


def test_broken_json():
    response = APIClient().post(
        reverse("users:login"), "{bad", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.json()["code"] == "parse_error"


def test_throttled(user):
    client = APIClient()
    data = {"email": "ivan@mail.com", "password": "Wrong-pass1!"}
    for _ in range(10):
        client.post(reverse("users:login"), data, format="json")

    response = client.post(reverse("users:login"), data, format="json")

    assert response.status_code == 429
    # DRF's own Ukrainian text is half English ("... Expected available in")
    assert response.json() == error("throttled", "Забагато запитів, спробуйте пізніше")
    assert "Retry-After" in response.headers


@pytest.mark.django_db
def test_browser_language_does_not_switch_to_english():
    # Browsers send Accept-Language themselves; the API stays Ukrainian.
    # Refresh, not login: login's limit is used up by test_throttled
    response = APIClient().post(
        reverse("users:refresh"),
        {"refresh": "not-a-token"},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
    )

    assert response.json() == error(
        "invalid_refresh_token", "Refresh-токен недійсний або прострочений"
    )
