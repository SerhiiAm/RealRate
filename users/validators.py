import string
import unicodedata

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

EMAIL_INVALID_MESSAGE = _("Please enter a valid email address")


def validate_email_domain(value):
    """Reject emails without a real domain.

    Django's EmailValidator accepts `x@localhost` and `x@[127.0.0.1]`.
    Other bad formats (no @, bad domain) are left to Django's validator,
    so only one error is shown.
    """
    _local, at, domain = value.rpartition("@")
    if at and ("." not in domain or domain.startswith("[")):
        raise ValidationError(EMAIL_INVALID_MESSAGE, code="invalid")


UKRAINIAN_LETTERS = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
NAME_LETTERS = frozenset(
    UKRAINIAN_LETTERS + UKRAINIAN_LETTERS.lower() + string.ascii_letters
)
# Hyphen and three apostrophes: ' (keyboard), ’ (typographic), ʼ (Ukrainian)
NAME_SYMBOLS = frozenset("-'’ʼ")
NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 20


def normalize_and_validate_name(value, message):
    """Return the name in NFC form or raise ValidationError(message).

    NFC: some keyboards (e.g. macOS) send "ї" as "і" + combining mark;
    after NFC it is one letter again.
    """
    name = unicodedata.normalize("NFC", value)
    is_valid = (
        NAME_MIN_LENGTH <= len(name) <= NAME_MAX_LENGTH
        and name[0] in NAME_LETTERS
        and set(name) <= NAME_LETTERS | NAME_SYMBOLS
    )
    if not is_valid:
        raise ValidationError(message, code="invalid")
    return name


ALLOWED_PASSWORD_CHARS = frozenset(
    string.ascii_letters + string.digits + string.punctuation
)


class PasswordRulesValidator:
    """Password rules agreed with PMs: one rule set, one error message.

    8-64 characters; only Latin letters, digits and ASCII special characters
    (so no spaces and no Cyrillic); at least 1 uppercase letter, 1 digit
    and 1 special character.
    """

    min_length = 8
    max_length = 64
    message = _(
        "Password must be 8–64 characters, include at least 1 uppercase letter, "
        "1 number, 1 special character, and no spaces"
    )

    def validate(self, password, user=None):
        is_valid = (
            self.min_length <= len(password) <= self.max_length
            and set(password) <= ALLOWED_PASSWORD_CHARS
            and any(char in string.ascii_uppercase for char in password)
            and any(char in string.digits for char in password)
            and any(char in string.punctuation for char in password)
        )
        if not is_valid:
            raise ValidationError(self.message, code="password_invalid")

    def get_help_text(self):
        return self.message
