import asyncio
import logging
import os
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.common.database import prices

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DERIBIT_API_URL = "https://www.deribit.com/api/v2/public/get_index_price"
TICKERS = ["btc_usd", "eth_usd"]


async def fetch_index_price(session: aiohttp.ClientSession, ticker: str):
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
                # return float(data["result"]["index_price"])
                price = data.get("result", {}).get("index_price")
                if price is not None:
                    return float(price)
                else:
                    logging.error(f"Не удалось найти 'index_price' в ответе для {ticker}. Ответ: {data}")
            else:
                logging.error(f"Ошибка API Deribit для {ticker}: Статус {response.status}")
    except aiohttp.ClientError as e:
        logging.error(f"Сетевая ошибка для {ticker}: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logging.error(f"Неожиданный формат ответа для {ticker}: {e}")
        return None
    return None


async def worker():
    """Основной рабочий цикл, собирающий данные каждую минуту."""
    async with aiohttp.ClientSession() as session:
        engine = create_async_engine(os.getenv("DATABASE_URL"))

        while True:
            data_to_insert = []

            start_time = time.time()
            current_timestamp = int(start_time)

            tasks = []
            async with asyncio.TaskGroup() as tg:
                for ticker in TICKERS:
                    task = tg.create_task(fetch_index_price(session, ticker))
                    tasks.append(task)
            prices_ = [task.result() for task in tasks]

            for ticker, price in zip(TICKERS, prices_):
                if price is not None:
                    data_to_insert.append({"ticker": ticker, "price": price, "timestamp": current_timestamp})

            try:
                async with engine.connect() as connection:
                    stmt_bulk = insert(prices)
                    await connection.execute(stmt_bulk, data_to_insert)
                    await connection.commit()
            finally:
                await engine.dispose()

            # Вычисляем время до следующего запуска, чтобы строго соблюдать интервал в 60 сек
            elapsed = time.time() - start_time
            sleep_time = max(0.0, 60.0 - elapsed)

            await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    if not os.getenv("DATABASE_URL"):
        load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env.light")
    try:
        asyncio.run(worker())
    except KeyboardInterrupt:
        logging.info("Работа клиента остановлена пользователем.")
