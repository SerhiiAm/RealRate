FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# gettext: makemessages / compilemessages (translations in locale/)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gettext && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==2.5.1

COPY pyproject.toml poetry.lock ./
RUN poetry install

COPY . .

RUN adduser --disabled-password --no-create-home appuser && \
    mkdir -p /app/media /app/staticfiles && \
    chown -R appuser:appuser /app/media /app/staticfiles
USER appuser

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
