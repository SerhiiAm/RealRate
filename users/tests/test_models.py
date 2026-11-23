import pytest
from django.contrib.auth import authenticate
from django.db import IntegrityError

from users.models import User

PASSWORD = "Str0ng-pass!"

pytestmark = pytest.mark.django_db


def test_create_user_lowercases_whole_email():
    user = User.objects.create_user("Ivan@Gmail.COM", PASSWORD)

    user.refresh_from_db()
    assert user.email == "ivan@gmail.com"


@pytest.mark.parametrize("email", ["", None])
def test_create_user_requires_email(email):
    with pytest.raises(ValueError, match="The Email field must be set"):
        User.objects.create_user(email, PASSWORD)

    assert not User.objects.exists()


def test_create_user_is_regular_user_with_hashed_password():
    user = User.objects.create_user("user@mail.com", PASSWORD)

    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.password != PASSWORD
    assert user.check_password(PASSWORD)


def test_create_superuser_has_admin_flags():
    user = User.objects.create_superuser("admin@mail.com", PASSWORD)

    assert user.is_staff is True
    assert user.is_superuser is True


@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("is_staff", "Superuser must have is_staff=True."),
        ("is_superuser", "Superuser must have is_superuser=True."),
    ],
)
def test_create_superuser_rejects_false_flag(flag, message):
    with pytest.raises(ValueError, match=message):
        User.objects.create_superuser("admin@mail.com", PASSWORD, **{flag: False})

    assert not User.objects.exists()


def test_database_rejects_same_email_in_other_case():
    # objects.create skips normalize_email, so only the DB constraint can stop it
    User.objects.create(email="Olga@Mail.com")

    with pytest.raises(IntegrityError, match="user_email_case_insensitive_unique"):
        User.objects.create(email="olga@mail.com")


def test_login_ignores_email_case():
    user = User.objects.create_user("admin@mail.com", PASSWORD)

    assert authenticate(email="ADMIN@Mail.com", password=PASSWORD) == user


def test_clean_lowercases_whole_email():
    # Admin forms call clean() instead of the manager
    user = User(email="Petro@Mail.COM")

    user.clean()

    assert user.email == "petro@mail.com"
