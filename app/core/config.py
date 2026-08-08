from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()

@dataclass(frozen=True)
class Settings:
    """Runtime configuration read only from environment variables."""

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/tickets.db")
    deepseek_api_key: str | None = os.getenv("DEEPSEEK_API_KEY") or None
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


settings = Settings()
