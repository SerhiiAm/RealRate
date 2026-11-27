# RealRate

Platform for honest ratings and reviews — backend API (Django + DRF).

## Status

Early setup. Ready: Django + DRF skeleton, PostgreSQL, Docker for local development,
custom User model (login by email, case-insensitive), user roles (user / admin),
auth API: registration, login, refresh, logout.
Not yet: profile (`/me`).

## Tech stack

- Python 3.13, Django 6.1, Django REST Framework
- PostgreSQL 17
- Poetry, Docker Compose
- djangorestframework-simplejwt (JWT authentication)
- Argon2 (password hashing)
- WhiteNoise (static files)
- drf-spectacular (Swagger API docs)
- pytest + pytest-django (tests)
- Black (formatter), Ruff (linter)

## Run with Docker

1. Copy `.env.example` to `.env` and fill in the values
   (generate `DJANGO_SECRET_KEY` with the command from the file).
2. Start:

   ```
   docker compose up -d --build
   ```

   Database migrations are applied automatically on start.

3. Create an admin account (asks for email and password):

   ```
   docker compose exec web python manage.py createsuperuser
   ```

4. Open http://localhost:8000/api/docs/ (Swagger) or http://localhost:8000/admin/

Useful commands:

```
docker compose logs -f web   # Django logs
docker compose down          # stop (data is kept)
docker compose down -v       # stop and DELETE database and uploaded files
```

Code changes are picked up automatically, no restart needed.
After pulling new migrations: `docker compose exec web python manage.py migrate`.
After changing dependencies, rebuild: `docker compose up -d --build`.

## Run without Docker (IDE)

The database still runs in Docker:

```
docker compose up -d db
poetry install
```

Django does not read `.env` by itself — load it in your IDE
(PyCharm: Run Configuration → Paths to ".env" files).

Migrations are not applied automatically here. After pulling new code, run
`manage.py migrate` from your IDE (same Run Configuration with `.env`).

## Access

- Every endpoint requires a logged-in user (`Authorization: Bearer <access>`),
  otherwise `401`.
- Open to everyone: registration, login, refresh, logout and API docs
  (`/api/docs/`, `/api/schema/`).

## Errors

Every error has the same format. `code` never changes, check it in code;
`message` is text for people and may change.

`message` is always in Ukrainian, whatever language the browser asks for.

```
{"code": "invalid_credentials", "message": "Неправильний email або пароль"}
```

Field errors (`400`) list all fields at once:

```
{"code": "validation_error", "message": "Некоректні дані",
 "fields": {"email": [{"code": "email_taken", "message": "Цей email уже зареєстровано"}]}}
```

Field codes:

| Code | When |
|---|---|
| `required` | field is missing, empty or `null` |
| `invalid` | wrong format (email, first or last name) |
| `max_length` | email longer than 254 characters |
| `email_taken` | email is already registered |
| `password_invalid` | password breaks the rules (length, letters, digits, special characters, spaces) |
| `password_too_common` | password is too common |
| `password_too_similar` | password is too similar to the email or name |
| `passwords_do_not_match` | `password_confirm` differs from `password` |

Other codes:

| Code | Status | When |
|---|---|---|
| `invalid_credentials` | 401 | wrong email or password, or deactivated account (login) |
| `invalid_refresh_token` | 401 | refresh token expired, already used or logged out |
| `throttled` | 429 | too many login attempts |
| `parse_error` | 400 | request body is not valid JSON |
| `method_not_allowed` | 405 | wrong HTTP method |
| `unsupported_media_type` | 415 | request body is not JSON or a form (e.g. `text/plain`) |
| `not_acceptable` | 406 | client asks for a response format other than JSON |
| `not_authenticated` | 401 | no access token (with `/me` and other protected endpoints) |
| `token_not_valid` | 401 | access token broken or expired (with `/me` and other protected endpoints) |
| `user_inactive` / `user_not_found` | 401 | access token of a deactivated / deleted user (with `/me` and other protected endpoints) |
| `permission_denied` | 403 | not allowed for this user (with upcoming endpoints: places, reviews) |
| `not_found` | 404 | object does not exist (with upcoming endpoints: places, reviews) |

Server errors (`500`) and unknown URLs (`404`) are not in this format.

## Users

- Login by **email + password**, there is no username.
- Email is case-insensitive: `Ivan@Mail.com` and `ivan@mail.com` are the same
  account. Emails are stored in lowercase.
- One account per email (duplicates are rejected, also by the database).
- Email must have a real domain: `x@localhost` and `x@[127.0.0.1]` are rejected.
- Password: 8–64 characters, at least 1 uppercase letter, 1 digit and
  1 special character; only Latin letters, digits and special characters,
  no spaces. It also must not be too common or too similar to the email/name.
  Passwords are stored hashed (Argon2). These rules apply everywhere,
  including the admin panel and `createsuperuser`.
- Every user has a role: `user` (default) or `admin`.
- Access to the admin panel (`/admin/`) depends only on the role: `admin` has
  full access, `user` has none.
- `createsuperuser` always creates a user with role `admin`.
- An admin can change other users' role and active status in the admin panel,
  but not their own (so nobody locks themselves out).

### Registration

- Fields: `email`, `first_name`, `password`, `password_confirm` are required;
  `last_name` is optional (stored as empty).
- First and last name: 2–20 characters, start with a letter; only Ukrainian
  or Latin letters, hyphen and apostrophes (`'` `’` `ʼ`); no spaces or digits.
  Letters `Ё Ъ Ы Э` are not accepted.
- Registration also logs the user in: the response has the user and a token
  pair (access lives 15 minutes, refresh 3 days).
- A new user always gets role `user`; `role`, `is_staff` and other extra
  fields in the request are ignored.
- Errors are returned per field, all at once (see [Errors](#errors)).
- Registration counts as the first login (`last_login` is set).

### Login, refresh and logout

- Login: email (any case) + password. The response is the same as for
  registration: the user and a token pair. `last_login` is updated.
- A wrong password, an unknown email and a deactivated account all get the
  same error: `401`, code `invalid_credentials`.
- At most 10 login attempts per minute from one IP; then `429`, even with
  the right password.
- Refresh: send the refresh token, get a new pair. A refresh token works
  only once: after it is exchanged, it stops working.
- Sending an already exchanged refresh token again is treated as theft:
  all sessions of that user are ended, the user has to log in again.
  Two refreshes with the same token at the same moment (e.g. two browser
  tabs) count as this too, so only one refresh may run at a time.
- Logout: send the refresh token, it stops working; other devices stay
  logged in. Logging out again with the same token is not an error (`204`).
- The access token can't be revoked: after logout it still works until it
  expires (max 15 minutes), so the frontend must delete both tokens.
- If the refresh token can't be used (expired, already used, logged out,
  account deactivated), the answer is always
  `401`, code `invalid_refresh_token`: the user has to log
  in again.

API endpoints are documented in Swagger: http://localhost:8000/api/docs/

## Tests

```
docker compose exec web pytest
```

Tests use a separate database (`test_<POSTGRES_DB>`), created and deleted automatically.

## Code quality

```
poetry run black .
poetry run ruff check .
```

## Translations

Texts in code are English, wrapped in `_()`; Ukrainian translations are in
`locale/uk/LC_MESSAGES/django.po`. After adding or changing a text:

```
docker compose exec web python manage.py makemessages -l uk --ignore=.venv --ignore=staticfiles --ignore=media
# fill in the empty msgstr "" in django.po, then:
docker compose exec web python manage.py compilemessages --ignore=.venv
```

Commit both `django.po` and `django.mo`. Without `--ignore=.venv` the
commands also go through the installed packages.
