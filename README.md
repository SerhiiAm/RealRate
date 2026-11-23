# RealRate

Platform for honest ratings and reviews — backend API (Django + DRF).

## Status

Early setup. Ready: Django + DRF skeleton, PostgreSQL, Docker for local development,
custom User model (login by email).
Not yet: API endpoints.

## Tech stack

- Python 3.13, Django 6.1, Django REST Framework
- PostgreSQL 17
- Poetry, Docker Compose
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

## Code quality

```
poetry run black .
poetry run ruff check .
```
