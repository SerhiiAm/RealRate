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
- Errors are returned per field, all at once: `{"email": ["..."]}`.
- Registration counts as the first login (`last_login` is set).

### Login, refresh and logout

- Login: email (any case) + password. The response is the same as for
  registration: the user and a token pair. `last_login` is updated.
- A wrong password, an unknown email and a deactivated account all get the
  same error: `401 {"detail": "Invalid email or password"}`.
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
  `401 {"detail": "Invalid or expired refresh token"}`: the user has to log
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
