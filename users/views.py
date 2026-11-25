from django.contrib.auth.models import update_last_login
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    AuthResponseSerializer,
    LoginSerializer,
    RefreshSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserSerializer,
)
from .tokens import rotate_refresh_token


def auth_response_data(user):
    """User block + new JWT pair (the refresh token is recorded for blacklisting)."""
    refresh = RefreshToken.for_user(user)
    return {
        "user": UserSerializer(user).data,
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


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

        # One transaction: if tokens fail, the user is not left half-registered
        with transaction.atomic():
            user = serializer.save()
            update_last_login(None, user)  # analytics: registration = first login
            data = auth_response_data(user)

        return Response(data, status=status.HTTP_201_CREATED)


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

        with transaction.atomic():
            update_last_login(None, user)
            data = auth_response_data(user)

        return Response(data, status=status.HTTP_200_OK)


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
