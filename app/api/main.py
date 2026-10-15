from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query, Depends
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection

from app.common.database import prices
from app.light.settings import get_settings

# асинхронный фреймворк, и настройки для асинхронного режима работы
cfg = get_settings()

engine = create_async_engine(
    cfg.DATABASE_URL,
    echo=False,
    pool_size=10,       # Базовое число соединений в пуле
    max_overflow=20,    # Дополнительные соединения сверх pool_size при пиковой нагрузке
    pool_timeout=30,    # Таймаут ожидания соединения из пула (в секундах)
    pool_recycle=1800,  # Время жизни соединения в секундах (сброс старых соединений)
    pool_pre_ping=True  # Проверка работоспособности соединения перед выдачей из пула
)

async def get_db() -> AsyncGenerator[AsyncConnection, None]:
    async with engine.connect() as connection:  # можно begin, но все приложение только читает, посчитал overhead
        yield connection

app = FastAPI()


@app.get("/api/v1/prices")
async def get_all_prices(
        ticker: str = Query(..., description="Тикер валюты (например, btc_usd)"),
        limit: int = Query(100, ge=1, le=1000, description="Количество записей (max 1000)"),
        offset: int = Query(0, ge=0, description="Смещение"),
        db = Depends(get_db)
):
    sth = select(prices).where(prices.c.ticker==ticker.lower()).order_by(prices.c.timestamp.desc()).limit(limit).offset(offset)
    result = await db.execute(sth)
    rows = result.mappings().all()
    return [dict(row) for row in rows]


@app.get("/api/v1/prices/latest")
async def get_latest_price(
        ticker: str = Query(..., description="Тикер валюты"),
        db = Depends(get_db)
):
    sth = select(prices).where(prices.c.ticker==ticker.lower()).order_by(prices.c.timestamp.desc()).limit(1)
    result = await db.execute(sth)
    rows = result.mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Данные для тикера '{ticker}' не найдены")

    return dict(rows[0])


@app.get("/api/v1/prices/search")
async def get_prices_by_date(
        ticker: str = Query(..., description="Тикер валюты"),
        start_date: datetime = Query(..., description="Начало периода (ISO формат: YYYY-MM-DDTHH:MM:SS)"),
        end_date: datetime = Query(..., description="Конец периода (ISO формат: YYYY-MM-DDTHH:MM:SS)"),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        db = Depends(get_db)
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date не может быть больше end_date")

    # Переводим входящую datetime в UNIX timestamp, как требует формат хранения в БД по ТЗ
    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())

    sth = (select(prices).where(
                and_(
                    prices.c.ticker == ticker.lower(),
                    prices.timestamp.between(start_ts, end_ts)
                )
            )
           .order_by(prices.c.timestamp.desc())
           .limit(limit)
           .offset(offset)
    )

    result = await db.execute(sth)
    rows = result.mappings().all()
    return [dict(row) for row in rows]
