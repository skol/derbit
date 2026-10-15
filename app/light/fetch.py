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
from app.common.fetch import fetch_index_price
from app.light.settings import get_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

cfg = get_settings()

async def worker():
    """Основной рабочий цикл, собирающий данные каждую минуту."""
    engine = create_async_engine(cfg.DATABASE_URL)

    async with aiohttp.ClientSession() as session:
        logging.info("Воркер запущен. Начинаем сбор данных...")

        while True:
            start_time = time.time()
            current_timestamp = int(start_time)
            data_to_insert = []

            try:
                async with asyncio.TaskGroup() as tg:
                    tasks = [tg.create_task(fetch_index_price(session, ticker)) for ticker in cfg.TICKERS]

                prices_ = [task.result() for task in tasks]

                for ticker, price in zip(cfg.TICKERS, prices_):
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
                    logging.info(f"Успешно сохранено {len(data_to_insert)} записей.")
                else:
                    logging.warning("Нет валидных данных для сохранения (возможно, сбой API).")

            except Exception as e:
                logging.error(f"Непредвиденная ошибка в цикле worker: {e}", exc_info=True)

            elapsed = time.time() - start_time
            sleep_time = max(0.0, 60.0 - elapsed)

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    if not os.getenv("DATABASE_URL"):
        load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env.light")

    try:
        asyncio.run(worker())
    except KeyboardInterrupt:
        logging.info("Работа воркера остановлена пользователем (Ctrl+C).")
    finally:
        logging.info("Завершение работы.")