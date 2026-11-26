import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from users.models import User

pytestmark = pytest.mark.django_db


class NewEndpointView(APIView):
    """Stands for any future endpoint that does not set its own permissions."""

    def get(self, request):
        return Response({"ok": True})


def call_new_endpoint(**headers):
    request = APIRequestFactory().get("/new-endpoint/", **headers)
    return NewEndpointView.as_view()(request)


def test_new_endpoint_requires_login():
    response = call_new_endpoint()

    assert response.status_code == 401


def test_new_endpoint_works_with_access_token():
    user = User.objects.create_user("ivan@mail.com", "Str0ng-pass!")
    access = AccessToken.for_user(user)

    response = call_new_endpoint(HTTP_AUTHORIZATION=f"Bearer {access}")

    assert response.status_code == 200


@pytest.mark.parametrize("url", ["/api/docs/", "/api/schema/"])
def test_api_docs_are_public(url):
    response = APIClient().get(url)

    assert response.status_code == 200
