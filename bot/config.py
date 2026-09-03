from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when required environment settings are invalid."""


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    owner_id: int
    payment_details: str
    price_per_star_rub: Decimal
    min_stars: int
    max_stars: int
    database_path: Path


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Переменная {name} не задана")
    return value


def load_config(env_file: str | Path = ".env") -> Config:
    load_dotenv(env_file)

    try:
        owner_id = int(_required("OWNER_ID"))
    except ValueError as exc:
        raise ConfigError("OWNER_ID должен быть числовым Telegram ID") from exc

    try:
        price = Decimal(_required("PRICE_PER_STAR_RUB")).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ConfigError("PRICE_PER_STAR_RUB должен быть числом") from exc
    if price <= 0:
        raise ConfigError("PRICE_PER_STAR_RUB должен быть больше нуля")

    try:
        min_stars = int(os.getenv("MIN_STARS", "50"))
        max_stars = int(os.getenv("MAX_STARS", "100000"))
    except ValueError as exc:
        raise ConfigError("MIN_STARS и MAX_STARS должны быть целыми числами") from exc
    if min_stars <= 0 or max_stars < min_stars:
        raise ConfigError("Проверьте диапазон MIN_STARS/MAX_STARS")

    payment_details = _required("PAYMENT_DETAILS").replace("\\n", "\n")

    return Config(
        bot_token=_required("BOT_TOKEN"),
        owner_id=owner_id,
        payment_details=payment_details,
        price_per_star_rub=price,
        min_stars=min_stars,
        max_stars=max_stars,
        database_path=Path(os.getenv("DATABASE_PATH", "data/orders.db")),
    )
