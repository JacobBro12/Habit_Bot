import asyncio
import logging
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import db
from storage import PgStorage

log = logging.getLogger("main")

COMMANDS = [
    BotCommand(command="start", description="Yangi maqsad qo'yish"),
    BotCommand(command="holat", description="Bugungi holat"),
    BotCommand(command="jadval", description="Habit tracker jadvali"),
    BotCommand(command="reset", description="Qaytadan boshlash"),
    BotCommand(command="yordam", description="Yordam"),
]


async def health(request):
    return web.Response(text="ok")


def db_host():
    try:
        return urlparse(config.DATABASE_URL).hostname or "?"
    except ValueError:
        return "noto'g'ri URL"


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    missing = [n for n in ("BOT_TOKEN", "GEMINI_API_KEY", "DATABASE_URL") if not getattr(config, n)]
    if missing:
        log.error("Environment'da yo'q o'zgaruvchilar: %s", ", ".join(missing))
        raise SystemExit(1)

    import handlers
    import scheduler

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=PgStorage())
    dp.include_router(handlers.router)

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    path = f"/webhook/{config.WEBHOOK_SECRET}"
    if config.WEBHOOK_BASE_URL:
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.WEBHOOK_SECRET).register(app, path=path)
        setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    log.info("HTTP server %s portda ishga tushdi", config.PORT)

    task = None
    try:
        log.info("Bazaga ulanilmoqda: %s", db_host())
        try:
            await db.init()
        except Exception:
            log.exception("BAZAGA ULANIB BO'LMADI (host: %s). DATABASE_URL ni tekshiring", db_host())
            raise SystemExit(1)
        log.info("Baza tayyor")

        await bot.set_my_commands(COMMANDS)
        task = asyncio.create_task(scheduler.run(bot))
        if config.WEBHOOK_BASE_URL:
            await bot.set_webhook(
                config.WEBHOOK_BASE_URL + path,
                secret_token=config.WEBHOOK_SECRET,
                allowed_updates=dp.resolve_used_update_types(),
            )
            log.info("Webhook rejimi: %s", config.WEBHOOK_BASE_URL)
            await asyncio.Event().wait()
        else:
            await bot.delete_webhook()
            log.info("Polling rejimi")
            await dp.start_polling(bot)
    finally:
        if task:
            task.cancel()
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
