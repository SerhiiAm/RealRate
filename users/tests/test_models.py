import pytest
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction

from users.models import Role, User

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

    user.refresh_from_db()
    assert user.role == Role.USER
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.password != PASSWORD
    assert user.check_password(PASSWORD)


def test_create_user_ignores_admin_flags_without_admin_role():
    # Second line of defence: flags alone must not make an admin
    user = User.objects.create_user(
        "user@mail.com", PASSWORD, is_staff=True, is_superuser=True
    )

    user.refresh_from_db()
    assert user.role == Role.USER
    assert user.is_staff is False
    assert user.is_superuser is False


def test_create_superuser_has_admin_role_and_flags():
    user = User.objects.create_superuser("admin@mail.com", PASSWORD)

    user.refresh_from_db()
    assert user.role == Role.ADMIN
    assert user.is_staff is True
    assert user.is_superuser is True


def test_create_superuser_rejects_non_admin_role():
    with pytest.raises(ValueError, match="Superuser must have role=admin."):
        User.objects.create_superuser("admin@mail.com", PASSWORD, role=Role.USER)

    assert not User.objects.exists()


@pytest.mark.parametrize(
    ("old_role", "new_role", "expected_flag"),
    [
        (Role.USER, Role.ADMIN, True),
        (Role.ADMIN, Role.USER, False),
    ],
)
@pytest.mark.parametrize("update_fields", [None, ["role"]])
def test_changing_role_syncs_flags_in_db(
    old_role, new_role, expected_flag, update_fields
):
    user = User.objects.create_user("user@mail.com", PASSWORD, role=old_role)

    user.role = new_role
    user.save(update_fields=update_fields)

    user.refresh_from_db()
    assert user.role == new_role
    assert user.is_staff is expected_flag
    assert user.is_superuser is expected_flag


@pytest.mark.parametrize(
    "changes",
    [
        {"role": Role.ADMIN},  # role without flags
        {"role": Role.ADMIN, "is_staff": True},  # admin without superuser
        {"is_superuser": True},  # flag without role
        {"is_staff": True},
    ],
)
def test_database_rejects_role_and_flags_mismatch(changes):
    # QuerySet.update() skips save(), so only the DB constraint can stop it
    user = User.objects.create_user("user@mail.com", PASSWORD)

    with (
        pytest.raises(IntegrityError, match="user_role_matches_admin_flags"),
        transaction.atomic(),
    ):
        User.objects.filter(pk=user.pk).update(**changes)

    user.refresh_from_db()
    assert user.role == Role.USER
    assert user.is_staff is False
    assert user.is_superuser is False


def test_full_clean_accepts_role_change():
    # Admin forms call full_clean() before save(): flags must be synced by then
    user = User.objects.create_user("user@mail.com", PASSWORD)
    user.role = Role.ADMIN

    user.full_clean()

    assert user.is_staff is True
    assert user.is_superuser is True


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
