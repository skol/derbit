import asyncio
import logging
import time

import aiohttp
from celery import Celery
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.common.database import prices
from app.common.fetch import fetch_index_price
from app.hard.settings import get_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

cfg = get_settings()
REDIS_URL = cfg.REDIS_URL
DATABASE_URL = cfg.DATABASE_URL
TICKERS = cfg.TICKERS

celery_app = Celery(
    "hard",
    broker=REDIS_URL,
    backend=REDIS_URL,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "fetch-prices-every-minute": {
        "task": "app.hard.fetch.fetch_prices_task",
        "schedule": 60.0,
    },
}


async def _fetch_and_save_prices():
    """
    Логика подобная лайтовой версии, но с учетом специфики celery
    """
    # Создаем движок для этой задачи (для тестового задания, в продакшене лучше переиспользовать глобальный engine)
    engine = create_async_engine(DATABASE_URL)

    try:
        async with aiohttp.ClientSession() as session:
            current_timestamp = int(time.time())
            data_to_insert = []

            tasks = [fetch_index_price(session, ticker) for ticker in TICKERS]
            prices_ = await asyncio.gather(*tasks)

            for ticker, price in zip(TICKERS, prices_):
                if price is not None:
                    data_to_insert.append({
                        "ticker": ticker,
                        "price": price,
                        "timestamp": current_timestamp
                    })

            if data_to_insert:
                async with engine.connect() as connection:
                    stmt_bulk = insert(prices)
                    await connection.execute(stmt_bulk, data_to_insert)
                    await connection.commit()
                logging.info(f"[Celery Task] Успешно сохранено {len(data_to_insert)} записей.")
            else:
                logging.warning("[Celery Task] Нет валидных данных для сохранения.")

    finally:
        await engine.dispose()

@celery_app.task(name="app.hard.fetch.fetch_prices_task")
def fetch_prices_task():
    """
    Синхронная обертка для асинхронной логики.
    asyncio.run() создает новый, чистый event loop для каждой задачи,
    что предотвращает конфликты "Event loop is already running" в Celery.
    """
    logging.info("Задача fetch_prices_task запущена!")
    try:
        asyncio.run(_fetch_and_save_prices())
    except Exception as e:
        logging.error(f"Критическая ошибка в задаче Celery: {e}", exc_info=True)
