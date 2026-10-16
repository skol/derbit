"""Тесты клиента Deribit — ``app/common/fetch.py`` (``fetch_index_price``).

Сеть не используется: ``aiohttp.ClientSession.get`` подменяется ``unittest.mock``.

Примечание: ``aioresponses`` (0.7.9) несовместим с ``aiohttp>=3.14`` —
реальный ``ClientResponse.__init__`` требует новый аргумент ``stream_writer``,
и мок-ответы падают с TypeError. Поэтому здесь используется ``MagicMock`` c
минимальной заглушкой ответа.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from app.common.fetch import DERIBIT_API_URL, fetch_index_price


class _FakeResponse:
    """Минимальная замена aiohttp.ClientResponse для мока ``session.get``."""

    def __init__(self, *, status: int = 200, payload: dict | None = None, body: str | None = None):
        self.status = status
        self._payload = payload
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def json(self):
        if self._body is not None:
            return json.loads(self._body)
        return self._payload


def _patch_get(session, handler):
    """Возвращает context manager, подменяющий ``session.get``."""
    return patch("aiohttp.ClientSession.get", handler)


# --- Парсинг ответа ---------------------------------------------------------


async def test_parses_index_price_for_btc():
    """Валидный ответ Deribit → корректный index_price для btc_usd."""
    mock_get = MagicMock(
        return_value=_FakeResponse(
            payload={
                "jsonrpc": "2.0",
                "result": {"index_price": 11628.81, "estimated_delivery_price": 11628.81},
                "id": 123,
            }
        )
    )

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert isinstance(price, float)
    assert price == pytest.approx(11628.81)


async def test_parses_index_price_for_eth():
    """Валидный ответ Deribit → корректный index_price для eth_usd."""
    mock_get = MagicMock(
        return_value=_FakeResponse(
            payload={"jsonrpc": "2.0", "result": {"index_price": 2500.5}, "id": 1}
        )
    )

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "eth_usd")

    assert isinstance(price, float)
    assert price == pytest.approx(2500.5)


# --- Формирование запроса ---------------------------------------------------


async def test_request_uses_correct_endpoint_and_params():
    """Запрос уходит на /public/get_index_price с параметром index_name=btc_usd."""
    mock_get = MagicMock(return_value=_FakeResponse(payload={"result": {"index_price": 1.0}}))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            await fetch_index_price(session, "btc_usd")

    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == DERIBIT_API_URL
    assert kwargs["params"] == {"index_name": "btc_usd"}


async def test_request_uses_ticker_specific_param():
    """Для eth_usd в запросе должен быть index_name=eth_usd."""
    mock_get = MagicMock(return_value=_FakeResponse(payload={"result": {"index_price": 2.0}}))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            await fetch_index_price(session, "eth_usd")

    args, kwargs = mock_get.call_args
    assert args[0] == DERIBIT_API_URL
    assert kwargs["params"] == {"index_name": "eth_usd"}


# --- Обработка ошибок HTTP --------------------------------------------------


async def test_http_500_returns_none():
    """HTTP 500 → клиент не падает, возвращает None."""
    mock_get = MagicMock(return_value=_FakeResponse(status=500))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None


async def test_http_429_returns_none():
    """HTTP 429 (rate limit) → клиент не падает, возвращает None."""
    mock_get = MagicMock(return_value=_FakeResponse(status=429))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None


async def test_timeout_returns_none():
    """Таймаут запроса → клиент обрабатывает его и возвращает None."""
    mock_get = MagicMock(side_effect=asyncio.TimeoutError)

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None


async def test_network_error_returns_none():
    """Сетевая ошибка (ClientError) → клиент не падает, возвращает None."""
    mock_get = MagicMock(side_effect=aiohttp.ClientConnectionError("boom"))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None


# --- Обработка невалидного/пустого ответа -----------------------------------


async def test_missing_result_returns_none():
    """Нет поля result → None, а не KeyError в глубине."""
    mock_get = MagicMock(return_value=_FakeResponse(payload={"jsonrpc": "2.0", "id": 1}))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None


async def test_missing_index_price_returns_none():
    """Есть result, но нет index_price → None."""
    mock_get = MagicMock(return_value=_FakeResponse(payload={"result": {"other": 1}}))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None


async def test_error_field_returns_none():
    """Ответ содержит error → None."""
    mock_get = MagicMock(
        return_value=_FakeResponse(
            payload={"jsonrpc": "2.0", "error": {"code": -32602, "message": "bad"}, "id": 1}
        )
    )

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None


async def test_invalid_json_returns_none():
    """Невалидный JSON → None, а не необработанное исключение."""
    mock_get = MagicMock(return_value=_FakeResponse(body="not-a-json"))

    with _patch_get(None, mock_get):
        async with aiohttp.ClientSession() as session:
            price = await fetch_index_price(session, "btc_usd")

    assert price is None
