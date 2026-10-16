import logging

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DERIBIT_API_URL = "https://www.deribit.com/api/v2/public/get_index_price"
TICKERS = ["btc_usd", "eth_usd"]


async def fetch_index_price(session: aiohttp.ClientSession, ticker: str) -> float | None:
    """Асинхронный запрос цены индекса с биржи Deribit."""
    params = {"index_name": ticker}
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(DERIBIT_API_URL, params=params, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                if "error" in data:
                    logging.error(f"Deribit вернул ошибку для {ticker}: {data['error']}")
                    return None

                price = data.get("result", {}).get("index_price")
                if price is not None:
                    return float(price)
                logging.error(f"Не удалось найти 'index_price' для {ticker}. Ответ: {data}")
            else:
                logging.error(f"Ошибка API Deribit для {ticker}: Статус {response.status}")
    except aiohttp.ClientError as e:
        logging.error(f"Сетевая ошибка для {ticker}: {e}")
    except TimeoutError as e:
        logging.error(f"Таймаут для {ticker}: {e}")
    except (KeyError, ValueError, TypeError) as e:
        logging.error(f"Неожиданный формат ответа для {ticker}: {e}")

    return None
