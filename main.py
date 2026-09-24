import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import db
from storage import PgStorage

COMMANDS = [
    BotCommand(command="start", description="Yangi maqsad qo'yish"),
    BotCommand(command="holat", description="Bugungi holat"),
    BotCommand(command="jadval", description="Habit tracker jadvali"),
    BotCommand(command="reset", description="Qaytadan boshlash"),
    BotCommand(command="yordam", description="Yordam"),
]


async def health(request):
    return web.Response(text="ok")


async def serve(app):
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    return runner


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN or not config.GEMINI_API_KEY:
        raise SystemExit("BOT_TOKEN va GEMINI_API_KEY to'ldirilishi kerak")

    import handlers
    import scheduler

    await db.init()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=PgStorage())
    dp.include_router(handlers.router)
    await bot.set_my_commands(COMMANDS)

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    task = asyncio.create_task(scheduler.run(bot))
    runner = None
    try:
        if config.WEBHOOK_BASE_URL:
            path = f"/webhook/{config.WEBHOOK_SECRET}"
            SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.WEBHOOK_SECRET).register(app, path=path)
            setup_application(app, dp, bot=bot)
            runner = await serve(app)
            await bot.set_webhook(
                config.WEBHOOK_BASE_URL + path,
                secret_token=config.WEBHOOK_SECRET,
                allowed_updates=dp.resolve_used_update_types(),
            )
            logging.info("Webhook rejimi: %s", config.WEBHOOK_BASE_URL)
            await asyncio.Event().wait()
        else:
            runner = await serve(app)
            await bot.delete_webhook()
            logging.info("Polling rejimi")
            await dp.start_polling(bot)
    finally:
        task.cancel()
        if runner:
            await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
