"""Общие фикстуры для тестов проекта Deribit.

ВАЖНО: переменные окружения выставляются на уровне модуля ДО импорта
приложения, потому что ``app.hard.main`` и ``app.hard.fetch`` создают
глобальные ``engine``/``cfg`` при импорте (читают ``DATABASE_URL``/``REDIS_URL``
через ``get_settings()``). Если выставить окружение позже, движок будет
смотреть на прод-БД из ``.env``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TEST_DB_NAME = "deribit_test"
# Тесты запускаются с хоста, порт 5432 проброшен из docker-compose.
TEST_DB_HOST = "localhost"


def _load_env_file(path: Path) -> dict[str, str]:
    """Простой парсер .env-подобного файла (env.txt)."""
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip()
    return data


_env_file = _load_env_file(PROJECT_ROOT / ".env")

POSTGRES_USER = os.environ.get("POSTGRES_USER") or _env_file.get("POSTGRES_USER", "zerg")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD") or _env_file.get(
    "POSTGRES_PASSWORD", "bury"
)
POSTGRES_PORT = os.environ.get("POSTGRES_PORT") or _env_file.get("POSTGRES_PORT", "5432")

TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{TEST_DB_HOST}:{POSTGRES_PORT}/{TEST_DB_NAME}"
)

# Выставляем окружение ДО импорта приложения.
os.environ["POSTGRES_USER"] = POSTGRES_USER
os.environ["POSTGRES_PASSWORD"] = POSTGRES_PASSWORD
os.environ["POSTGRES_HOST"] = TEST_DB_HOST
os.environ["POSTGRES_PORT"] = str(POSTGRES_PORT)
os.environ["POSTGRES_DB"] = TEST_DB_NAME
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """Применяет схему к тестовой БД через ``alembic upgrade head`` (как в проде).

    ``metadata.create_all()`` намеренно не используется — это расхождение с продом.
    """
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # alembic/env.py читает DATABASE_URL из окружения и сам убирает "+asyncpg".
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Асинхронный движок на тестовую БД."""
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_prices(db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Очищает таблицу ``prices`` перед каждым тестом.

    Уникальный индекс ``idx_prices_ticker_timestamp`` не даёт вставлять
    одинаковые (ticker, timestamp) повторно, поэтому изоляция обязательна.
    """
    from app.common.database import prices

    async with db_engine.begin() as conn:
        await conn.execute(delete(prices))
    yield


@pytest_asyncio.fixture
async def api_client():
    """HTTP-клиент поверх ASGI-приложения FastAPI (без реального сервера).

    Глобальный engine в app.hard.main создаётся при импорте с QueuePool.
    pytest-asyncio закрывает event loop после каждого теста (function scope),
    а пул соединений переживает loop — отсюда ``Event loop is closed`` при
    повторном использовании. Поэтому engine переопределяется на NullPool: каждое
    соединение создаётся заново в текущем loop теста.
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.hard import main as main_module

    main_module.engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
