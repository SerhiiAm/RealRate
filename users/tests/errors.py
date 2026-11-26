"""Expected error bodies (format from config/exceptions.py)."""


def error(code, message):
    return {"code": code, "message": message}


def invalid_input(fields):
    """{"email": [("email_taken", "...")]} -> the full 400 body."""
    return {
        "code": "validation_error",
        "message": "Invalid input",
        "fields": {
            field: [error(code, message) for code, message in items]
            for field, items in fields.items()
        },
    }
