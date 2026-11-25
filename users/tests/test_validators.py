import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from users.models import User
from users.validators import PasswordRulesValidator

RULES_MESSAGE = (
    "Password must be 8–64 characters, include at least 1 uppercase letter, "
    "1 number, 1 special character, and no spaces"
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
        ("Password1!", "user@mail.com", "This password is too common."),
        (
            "Ivanenko1!",
            "ivanenko@mail.com",
            "The password is too similar to the email address.",
        ),
    ],
)
def test_validate_password_uses_project_validators(password, email, message):
    with pytest.raises(ValidationError) as exc_info:
        validate_password(password, user=User(email=email))

    assert message in exc_info.value.messages


def test_validate_password_accepts_strong_password():
    validate_password("Str0ng-pass!", user=User(email="user@mail.com"))
