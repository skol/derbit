"""Тесты слоя работы с БД (таблица ``prices`` из ``app/common/database.py``).

Отдельного репозитория в проекте нет: запросы к БД живут прямо в
``app/hard/main.py`` (FastAPI) и ``app/hard/fetch.py`` (Celery). Поэтому здесь
проверяются те же SQL-операции (insert/select/between/order_by) напрямую через
SQLAlchemy Core на тестовой БД.
"""

from __future__ import annotations

import pytest
from sqlalchemy import and_, insert, select

from app.common.database import prices


async def _insert(engine, rows: list[dict]) -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(prices), rows)


async def _select_by_ticker(engine, ticker: str):
    async with engine.connect() as conn:
        result = await conn.execute(select(prices).where(prices.c.ticker == ticker))
        return result.mappings().all()


async def _select_latest(engine, ticker: str):
    async with engine.connect() as conn:
        result = await conn.execute(
            select(prices)
            .where(prices.c.ticker == ticker)
            .order_by(prices.c.timestamp.desc())
            .limit(1)
        )
        return result.mappings().first()


async def _select_between(engine, ticker: str, start_ts: int, end_ts: int):
    async with engine.connect() as conn:
        result = await conn.execute(
            select(prices).where(
                and_(prices.c.ticker == ticker, prices.c.timestamp.between(start_ts, end_ts))
            )
        )
        return result.mappings().all()


# --- Запись -----------------------------------------------------------------


async def test_insert_stores_ticker_price_timestamp(db_engine):
    """Запись сохраняется в правильные поля: ticker, price, timestamp."""
    await _insert(db_engine, [{"ticker": "btc_usd", "price": 100.5, "timestamp": 1700000000}])

    rows = await _select_by_ticker(db_engine, "btc_usd")

    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "btc_usd"
    assert float(row["price"]) == pytest.approx(100.5)
    assert row["timestamp"] == 1700000000


# --- Чтение по тикеру -------------------------------------------------------


async def test_read_by_ticker_does_not_mix_currencies(db_engine):
    """btc не путается с eth: возвращаются только записи нужной валюты."""
    await _insert(
        db_engine,
        [
            {"ticker": "btc_usd", "price": 1, "timestamp": 100},
            {"ticker": "eth_usd", "price": 2, "timestamp": 100},
        ],
    )

    btc = await _select_by_ticker(db_engine, "btc_usd")
    eth = await _select_by_ticker(db_engine, "eth_usd")

    assert [r["ticker"] for r in btc] == ["btc_usd"]
    assert [r["ticker"] for r in eth] == ["eth_usd"]


# --- Последняя цена ---------------------------------------------------------


async def test_latest_price_returns_max_timestamp(db_engine):
    """Возвращается запись с максимальным timestamp, а не «случайная»."""
    await _insert(
        db_engine,
        [
            {"ticker": "btc_usd", "price": 1, "timestamp": 300},
            {"ticker": "btc_usd", "price": 2, "timestamp": 100},
            {"ticker": "btc_usd", "price": 3, "timestamp": 200},
        ],
    )

    row = await _select_latest(db_engine, "btc_usd")

    assert row is not None
    assert row["timestamp"] == 300
    assert float(row["price"]) == pytest.approx(1)


# --- Фильтр по дате ---------------------------------------------------------


async def test_filter_by_date_includes_bounds(db_engine):
    """Границы from/to включительны (between)."""
    await _insert(
        db_engine,
        [
            {"ticker": "btc_usd", "price": 1, "timestamp": 100},
            {"ticker": "btc_usd", "price": 2, "timestamp": 200},
            {"ticker": "btc_usd", "price": 3, "timestamp": 300},
        ],
    )

    rows = await _select_between(db_engine, "btc_usd", 100, 300)

    assert {r["timestamp"] for r in rows} == {100, 200, 300}


async def test_filter_by_date_excludes_out_of_range(db_engine):
    """Записи вне диапазона не попадают в выборку."""
    await _insert(
        db_engine,
        [
            {"ticker": "btc_usd", "price": 1, "timestamp": 50},
            {"ticker": "btc_usd", "price": 2, "timestamp": 150},
            {"ticker": "btc_usd", "price": 3, "timestamp": 250},
        ],
    )

    rows = await _select_between(db_engine, "btc_usd", 100, 200)

    assert {r["timestamp"] for r in rows} == {150}


async def test_no_data_in_range_returns_empty_list(db_engine):
    """Нет данных в диапазоне → пустой список, а не ошибка."""
    await _insert(db_engine, [{"ticker": "btc_usd", "price": 1, "timestamp": 100}])

    rows = await _select_between(db_engine, "btc_usd", 200, 300)

    assert rows == []


async def test_from_greater_than_to_returns_empty_list(db_engine):
    """from > to на уровне БД → пустой список (не ошибка)."""
    await _insert(db_engine, [{"ticker": "btc_usd", "price": 1, "timestamp": 100}])

    rows = await _select_between(db_engine, "btc_usd", 300, 100)

    assert rows == []


# --- Пустая БД --------------------------------------------------------------


async def test_empty_db_returns_empty_list(db_engine):
    """Пустая БД: списочный запрос не падает, возвращает []."""
    rows = await _select_by_ticker(db_engine, "btc_usd")

    assert rows == []


async def test_empty_db_latest_returns_none(db_engine):
    """Пустая БД: одиночный запрос не падает, возвращает None (на API → 404)."""
    row = await _select_latest(db_engine, "btc_usd")

    assert row is None
