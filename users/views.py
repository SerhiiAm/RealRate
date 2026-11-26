from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from . import services
from .serializers import (
    AuthResponseSerializer,
    LoginSerializer,
    RefreshSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserSerializer,
)
from .tokens import revoke_refresh_token, rotate_refresh_token


def auth_response(user, tokens, status_code):
    """Response of register and login: user block + token pair."""
    return Response({"user": UserSerializer(user).data, **tokens}, status=status_code)


class PublicAuthViewMixin:
    """Settings for register / login / refresh / logout."""

    permission_classes = (AllowAny,)
    # No authentication: an old or broken access token that the frontend
    # sends with every request must not block these endpoints
    authentication_classes = ()

    def get_authenticate_header(self, request):
        # Without authentication classes DRF turns 401 into 403;
        # returning the header keeps "invalid credentials/token" a 401
        return 'Bearer realm="api"'


class RegisterView(PublicAuthViewMixin, generics.CreateAPIView):
    """Register and log in at once: the response already has the tokens."""

    serializer_class = RegisterSerializer

    @extend_schema(responses={201: AuthResponseSerializer})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, tokens = services.register(**serializer.validated_data)

        return auth_response(user, tokens, status.HTTP_201_CREATED)


class LoginView(PublicAuthViewMixin, generics.GenericAPIView):
    """Log in with email and password: user block + new token pair."""

    serializer_class = LoginSerializer
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "login"

    @extend_schema(responses={200: AuthResponseSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        tokens = services.log_in(user)

        return auth_response(user, tokens, status.HTTP_200_OK)


class RefreshView(PublicAuthViewMixin, generics.GenericAPIView):
    """Exchange a refresh token for a new pair; the old one stops working.

    Sending an already exchanged refresh token again ends all sessions
    of the user (it means the token was stolen).
    """

    serializer_class = RefreshSerializer

    @extend_schema(responses={200: TokenPairSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pair = rotate_refresh_token(serializer.validated_data["refresh"])

        return Response(pair, status=status.HTTP_200_OK)


class LogoutView(PublicAuthViewMixin, generics.GenericAPIView):
    """Log out of this session: the refresh token stops working.

    No access token needed (it may already be expired). The access token
    can't be revoked and stays valid until it expires (max 15 minutes),
    so the frontend must delete both tokens. Calling it again returns 204 too.
    """

    serializer_class = RefreshSerializer

    @extend_schema(responses={204: None})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        revoke_refresh_token(serializer.validated_data["refresh"])

        return Response(status=status.HTTP_204_NO_CONTENT)
