FROM python:3.12-slim AS base

# Не пишем .pyc, не буферизуем stdout — логи сразу видны в docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Системные зависимости:
# - build-essential нужен, если какие-то пакеты собираются из исходников (asyncpg обычно нет, но на всякий)
# - libpq не нужен, если ставишь psycopg2-binary; нужен, если psycopg2 (source)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Установка uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Копируем файлы зависимостей и устанавливаем их в системное окружение
COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml

# Копируем код приложения
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY ./app/common ./app/common
COPY ./app/hard ./app/hard

# Non-root пользователь
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 9999

# По умолчанию запускаем FastAPI
CMD ["uvicorn", "app.hard.main:app", "--host", "0.0.0.0", "--port", "9999"]
