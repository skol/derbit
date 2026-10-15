from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    DERIBIT_API_URL: str = "https://www.deribit.com/api/v2/public/get_index_price"
    TICKERS: List[str] = ["btc_usd", "eth_usd"]

    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "derbit"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    DATABASE_URL: str = ""
    REDIS_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent.parent / ".env.light" ,
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
