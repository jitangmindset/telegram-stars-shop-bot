from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import ConfigError, load_config
from bot.database import OrderRepository
from bot.handlers import router


async def main() -> None:
    config = load_config()
    orders = OrderRepository(config.database_path)
    orders.initialize()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(
        bot,
        config=config,
        orders=orders,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except ConfigError as exc:
        raise SystemExit(f"Ошибка конфигурации: {exc}") from exc
