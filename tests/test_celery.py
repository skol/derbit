"""Тесты Celery-задачи — ``app/hard/fetch.py`` (``fetch_prices_task``).

Клиент Deribit подменяется моком (в сеть не ходим), запись идёт в тестовую БД.

Задача синхронная и внутри вызывает ``asyncio.run(...)``. Чтобы не получить
``RuntimeError: asyncio.run() cannot be called from a running event loop``,
задача запускается в отдельном потоке через ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
from sqlalchemy import select

from app.common.database import prices
from app.hard.fetch import celery_app, fetch_prices_task

TASK_NAME = "app.hard.fetch.fetch_prices_task"


async def _select_all(engine):
    async with engine.connect() as conn:
        result = await conn.execute(select(prices))
        return result.mappings().all()


# --- Задача вызывает клиент и пишет в БД ------------------------------------


async def test_task_saves_two_records(monkeypatch, db_engine):
    """После вызова задачи в БД появляются 2 записи: btc_usd и eth_usd."""

    async def fake_fetch(session, ticker):
        return {"btc_usd": 100.0, "eth_usd": 200.0}[ticker]

    monkeypatch.setattr("app.hard.fetch.fetch_index_price", fake_fetch)

    await asyncio.to_thread(fetch_prices_task.apply)

    rows = await _select_all(db_engine)
    assert len(rows) == 2
    assert {row["ticker"] for row in rows} == {"btc_usd", "eth_usd"}


async def test_task_saves_correct_prices(monkeypatch, db_engine):
    """В БД сохраняются именно те цены, что вернул клиент."""

    async def fake_fetch(session, ticker):
        return {"btc_usd": 111.5, "eth_usd": 222.5}[ticker]

    monkeypatch.setattr("app.hard.fetch.fetch_index_price", fake_fetch)

    await asyncio.to_thread(fetch_prices_task.apply)

    rows = {row["ticker"]: float(row["price"]) for row in await _select_all(db_engine)}
    assert rows == {"btc_usd": 111.5, "eth_usd": 222.5}


async def test_task_saves_recent_unix_timestamp(monkeypatch, db_engine):
    """В сохранённую запись попадает UNIX timestamp в разумных пределах."""

    async def fake_fetch(session, ticker):
        return 100.0

    monkeypatch.setattr("app.hard.fetch.fetch_index_price", fake_fetch)

    before = int(time.time())
    await asyncio.to_thread(fetch_prices_task.apply)
    after = int(time.time())

    rows = await _select_all(db_engine)
    assert rows
    for row in rows:
        assert before <= row["timestamp"] <= after


# --- Регистрация задачи / расписание ----------------------------------------


def test_task_name_matches_beat_schedule():
    """Имя задачи совпадает с тем, что указано в beat-конфиге."""
    assert fetch_prices_task.name == TASK_NAME

    scheduled_task = celery_app.conf.beat_schedule["fetch-prices-every-minute"]["task"]
    assert scheduled_task == fetch_prices_task.name


def test_task_is_registered_in_celery_app():
    """Задача зарегистрирована в приложении Celery под ожидаемым именем."""
    assert TASK_NAME in celery_app.tasks


# --- Обработка ошибок клиента -----------------------------------------------


async def test_task_handles_unavailable_client(monkeypatch, db_engine, caplog):
    """Deribit недоступен (клиент вернул None) → задача не падает, пишет в лог."""

    async def fake_fetch(session, ticker):
        return None

    monkeypatch.setattr("app.hard.fetch.fetch_index_price", fake_fetch)

    with caplog.at_level(logging.WARNING):
        await asyncio.to_thread(fetch_prices_task.apply)

    rows = await _select_all(db_engine)
    assert rows == []
    assert any("Нет валидных данных" in record.message for record in caplog.records)


async def test_task_does_not_raise_on_client_exception(monkeypatch, db_engine, caplog):
    """Клиент поднял исключение → задача не роняет воркер, логирует ошибку."""

    async def raising_fetch(session, ticker):
        raise aiohttp.ClientError("deribit is down")

    monkeypatch.setattr("app.hard.fetch.fetch_index_price", raising_fetch)

    with caplog.at_level(logging.ERROR):
        # Не должно быть проброшенного исключения наружу.
        await asyncio.to_thread(fetch_prices_task.apply)

    rows = await _select_all(db_engine)
    assert rows == []
    assert any("Критическая ошибка" in record.message for record in caplog.records)
