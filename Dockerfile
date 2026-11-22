FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.5.1

COPY pyproject.toml poetry.lock ./
RUN poetry install

COPY . .

RUN adduser --disabled-password --no-create-home appuser && \
    mkdir -p /app/media && \
    chown -R appuser:appuser /app/media
USER appuser

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
