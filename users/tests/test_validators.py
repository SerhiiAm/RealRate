import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command

from users.models import User
from users.validators import PasswordRulesValidator, validate_email_domain

EMAIL_MESSAGE = "Введіть коректну адресу електронної пошти"

RULES_MESSAGE = (
    "Пароль має містити 8–64 символи, щонайменше 1 велику літеру, 1 цифру, "
    "1 спеціальний символ і не містити пробілів"
)


@pytest.mark.parametrize(
    "password",
    [
        "Abcdef1!",  # exactly 8
        "A1!" + "a" * 61,  # exactly 64
        "ABCDEF1.",  # no lowercase is fine
        "Qw3$" + "x" * 10,
    ],
)
def test_password_rules_accept_valid(password):
    PasswordRulesValidator().validate(password)


@pytest.mark.parametrize(
    "password",
    [
        "Abcde1!",  # 7 chars
        "A1!" + "a" * 62,  # 65 chars
        "abcdef1!",  # no uppercase
        "Abcdefg!",  # no digit
        "Abcdefg1",  # no special
        "Abcd ef1!",  # space
        "Abcdef1!\t",  # tab
        "Abcdef1!\n",  # trailing newline
        "Abcdef1!ї",  # Cyrillic letter
        "Пароль1!A",  # Cyrillic word
        "Abcdefg١!",  # Arabic-Indic digit, not 0-9
        "Abcdef1!😀",  # emoji
        "",
    ],
)
def test_password_rules_reject_invalid(password):
    with pytest.raises(ValidationError) as exc_info:
        PasswordRulesValidator().validate(password)

    assert exc_info.value.messages == [RULES_MESSAGE]


# Settings wiring: our rules + Django's similarity and common-password checks
@pytest.mark.parametrize(
    ("password", "email", "message"),
    [
        ("short", "user@mail.com", RULES_MESSAGE),
        ("Password1!", "user@mail.com", "Пароль занадто поширений."),
        (
            "Ivanenko1!",
            "ivanenko@mail.com",
            "Пароль надто схожий на email.",
        ),
    ],
)
def test_validate_password_uses_project_validators(password, email, message):
    with pytest.raises(ValidationError) as exc_info:
        validate_password(password, user=User(email=email))

    assert message in exc_info.value.messages


def test_validate_password_accepts_strong_password():
    validate_password("Str0ng-pass!", user=User(email="user@mail.com"))


@pytest.mark.parametrize("email", ["x@localhost", "x@[127.0.0.1]"])
def test_email_domain_rejects_no_real_domain(email):
    with pytest.raises(ValidationError) as exc_info:
        validate_email_domain(email)

    assert exc_info.value.messages == [EMAIL_MESSAGE]


@pytest.mark.parametrize(
    "email",
    [
        "ivan@mail.com",
        "io@i.ua",  # short real email
        "ivan@пошта.укр",  # Cyrillic domain is a real domain
        "abc",  # no @: left to Django's validator, so only one error is shown
    ],
)
def test_email_domain_accepts_others(email):
    validate_email_domain(email)


@pytest.mark.parametrize(
    ("email", "message"),
    [
        ("x@localhost", EMAIL_MESSAGE),  # our validator
        ("abc", "Введіть коректну адресу електронної пошти."),  # Django's validator
    ],
)
def test_user_email_field_shows_one_error(email, message):
    # Model field validation is what admin forms use
    with pytest.raises(ValidationError) as exc_info:
        User(email=email).full_clean(
            exclude=["password"], validate_unique=False, validate_constraints=False
        )

    assert exc_info.value.message_dict["email"] == [message]


@pytest.mark.django_db
def test_createsuperuser_rejects_localhost_email(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Str0ng-pass!")

    with pytest.raises(CommandError, match=EMAIL_MESSAGE):
        call_command("createsuperuser", "--noinput", email="x@localhost")

    assert not User.objects.exists()
