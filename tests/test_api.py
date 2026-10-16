"""Тесты FastAPI-приложения — ``app/hard/main.py``.

Запросы идут через ASGI-транспорт (без реального сервера), данные пишутся в
тестовую БД напрямую через SQLAlchemy Core.
"""

from __future__ import annotations

from sqlalchemy import insert

from app.common.database import prices

# 2023-11-14T22:13:20 UTC
TS = 1700000000
START_ISO = "2023-11-14T00:00:00"
END_ISO = "2023-11-15T00:00:00"


async def _insert(engine, rows: list[dict]) -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(prices), rows)


# --- Обязательный query-параметр ticker -------------------------------------


async def test_prices_without_ticker_returns_422(api_client):
    resp = await api_client.get("/api/v1/prices")
    assert resp.status_code == 422


async def test_prices_with_invalid_ticker_returns_422(api_client):
    resp = await api_client.get("/api/v1/prices", params={"ticker": "doge_usd"})
    assert resp.status_code == 422


async def test_prices_with_valid_ticker_returns_200(api_client, db_engine):
    await _insert(db_engine, [{"ticker": "btc_usd", "price": 100, "timestamp": TS}])

    resp = await api_client.get("/api/v1/prices", params={"ticker": "btc_usd"})

    assert resp.status_code == 200


async def test_latest_without_ticker_returns_422(api_client):
    resp = await api_client.get("/api/v1/prices/latest")
    assert resp.status_code == 422


async def test_latest_with_invalid_ticker_returns_422(api_client):
    resp = await api_client.get("/api/v1/prices/latest", params={"ticker": "doge_usd"})
    assert resp.status_code == 422


async def test_search_without_ticker_returns_422(api_client):
    resp = await api_client.get(
        "/api/v1/prices/search", params={"start_date": START_ISO, "end_date": END_ISO}
    )
    assert resp.status_code == 422


async def test_search_with_invalid_ticker_returns_422(api_client):
    resp = await api_client.get(
        "/api/v1/prices/search",
        params={"ticker": "doge_usd", "start_date": START_ISO, "end_date": END_ISO},
    )
    assert resp.status_code == 422


# --- Структура ответа -------------------------------------------------------


async def test_prices_response_structure(api_client, db_engine):
    await _insert(db_engine, [{"ticker": "btc_usd", "price": 100, "timestamp": TS}])

    resp = await api_client.get("/api/v1/prices", params={"ticker": "btc_usd"})
    data = resp.json()

    assert isinstance(data, list)
    assert len(data) == 1
    assert set(data[0].keys()) == {"id", "ticker", "price", "timestamp"}
    assert data[0]["ticker"] == "btc_usd"
    assert data[0]["timestamp"] == TS


async def test_latest_response_structure(api_client, db_engine):
    await _insert(db_engine, [{"ticker": "btc_usd", "price": 100, "timestamp": TS}])

    resp = await api_client.get("/api/v1/prices/latest", params={"ticker": "btc_usd"})
    data = resp.json()

    assert resp.status_code == 200
    assert isinstance(data, dict)
    assert set(data.keys()) == {"id", "ticker", "price", "timestamp"}


async def test_search_response_structure(api_client, db_engine):
    await _insert(db_engine, [{"ticker": "btc_usd", "price": 100, "timestamp": TS}])

    resp = await api_client.get(
        "/api/v1/prices/search",
        params={"ticker": "btc_usd", "start_date": START_ISO, "end_date": END_ISO},
    )
    data = resp.json()

    assert resp.status_code == 200
    assert isinstance(data, list)
    assert len(data) == 1
    assert set(data[0].keys()) == {"id", "ticker", "price", "timestamp"}


# --- Валидация формата даты -------------------------------------------------


async def test_search_invalid_date_format_returns_422(api_client):
    resp = await api_client.get(
        "/api/v1/prices/search",
        params={"ticker": "btc_usd", "start_date": "not-a-date", "end_date": END_ISO},
    )
    assert resp.status_code == 422


# --- Пустой результат -------------------------------------------------------


async def test_prices_empty_returns_200_empty_list(api_client):
    resp = await api_client.get("/api/v1/prices", params={"ticker": "btc_usd"})

    assert resp.status_code == 200
    assert resp.json() == []


async def test_search_empty_returns_200_empty_list(api_client):
    resp = await api_client.get(
        "/api/v1/prices/search",
        params={"ticker": "btc_usd", "start_date": START_ISO, "end_date": END_ISO},
    )

    assert resp.status_code == 200
    assert resp.json() == []


async def test_latest_empty_returns_404(api_client):
    resp = await api_client.get("/api/v1/prices/latest", params={"ticker": "btc_usd"})

    assert resp.status_code == 404


# --- Последняя цена ---------------------------------------------------------


async def test_latest_returns_max_timestamp(api_client, db_engine):
    await _insert(
        db_engine,
        [
            {"ticker": "btc_usd", "price": 1, "timestamp": TS - 100},
            {"ticker": "btc_usd", "price": 2, "timestamp": TS},
            {"ticker": "btc_usd", "price": 3, "timestamp": TS - 50},
        ],
    )

    resp = await api_client.get("/api/v1/prices/latest", params={"ticker": "btc_usd"})
    data = resp.json()

    assert resp.status_code == 200
    assert data["timestamp"] == TS


# --- Границы диапазона дат --------------------------------------------------


async def test_search_includes_bounds(api_client, db_engine):
    await _insert(
        db_engine,
        [
            {"ticker": "btc_usd", "price": 1, "timestamp": TS},
            {"ticker": "btc_usd", "price": 2, "timestamp": TS + 3600},
        ],
    )

    resp = await api_client.get(
        "/api/v1/prices/search",
        params={"ticker": "btc_usd", "start_date": START_ISO, "end_date": END_ISO},
    )
    data = resp.json()

    assert resp.status_code == 200
    assert {row["timestamp"] for row in data} == {TS, TS + 3600}


# --- from > to --------------------------------------------------------------


async def test_search_start_after_end_returns_422(api_client):
    resp = await api_client.get(
        "/api/v1/prices/search",
        params={"ticker": "btc_usd", "start_date": END_ISO, "end_date": START_ISO},
    )

    assert resp.status_code == 422
