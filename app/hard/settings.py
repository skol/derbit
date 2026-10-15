from functools import lru_cache
from typing import List, Literal, get_args

from pydantic_settings import BaseSettings, SettingsConfigDict


Ticker = Literal["btc_usd", "eth_usd"]
TICKERS: tuple[str, ...] = get_args(Ticker)

class Settings(BaseSettings):
    DERIBIT_API_URL: str = "https://www.deribit.com/api/v2/public/get_index_price"
    TICKERS: tuple[str, ...] = TICKERS

    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "derbit"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    DATABASE_URL: str = ""
    REDIS_URL: str = ""

    model_config = SettingsConfigDict(extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
