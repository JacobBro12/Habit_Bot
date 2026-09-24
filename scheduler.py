import asyncio
import html
import logging
from datetime import date, datetime, time, timedelta

from aiogram import Bot

import config
import db
import plan
import service

log = logging.getLogger(__name__)


def _overdue(day, now):
    status = day["status"]
    if status == "pending":
        return date.fromisoformat(day["day"]) < now.date()
    if status in ("running", "awaiting_report", "collecting_photos") and day["due_at"]:
        due = datetime.fromisoformat(day["due_at"])
        return now > due + timedelta(hours=config.REPORT_GRACE_HOURS)
    return False


async def _remind(bot: Bot, user, day, now):
    hour, minute = map(int, user["start_time"].split(":"))
    start_dt = datetime.combine(now.date(), time(hour, minute))
    if now < start_dt or day["reminders"] >= config.MAX_REMINDERS:
        return
    last = day["last_reminded_at"]
    if last and now - datetime.fromisoformat(last) < timedelta(minutes=config.REMINDER_INTERVAL_MIN):
        return
    await db.update_day(day["id"], reminders=day["reminders"] + 1, last_reminded_at=now.isoformat())

    days_left = (date.fromisoformat(user["end_date"]) - now.date()).days
    left_text = f"maqsad kuniga {days_left} kun qoldi" if days_left > 0 else "bugun maqsad kuni"
    tasks = plan.effective_tasks(day)
    prefix = "" if day["reminders"] == 0 else f"🔔 <b>Eslatma {day['reminders'] + 1}/{config.MAX_REMINDERS}</b>\n\n"
    text = (
        f"{prefix}Hurmatli <b>{html.escape(user['name'])}</b> foydalanuvchi, siz soat <b>{user['start_time']}</b>da "
        f"«{html.escape(user['goal'])}» maqsadingiz tomon harakat qilishingizni aytgansiz va {left_text}. "
        "Iltimos, harakatni boshlang!\n\n"
        f"<b>Bugungi vazifalar</b> (jami {plan.fmt_duration(plan.total_minutes(tasks))}):\n"
        f"{plan.format_tasks(tasks)}"
    )
    await bot.send_message(
        user["chat_id"], text, reply_markup=service.kb([("▶️ Boshladim", f"start:{day['id']}")])
    )


async def process_user(bot: Bot, user, now):
    uid = user["user_id"]
    for d0 in await db.get_days(uid):
        day = await db.get_day(d0["id"])
        if _overdue(day, now):
            await service.roll_missed(bot, user, day)
    for d0 in await db.get_days(uid):
        day = await db.get_day(d0["id"])
        if day["status"] == "running" and now >= datetime.fromisoformat(day["due_at"]):
            await service.ask_report(bot, day)
        elif day["status"] == "pending" and day["day"] == now.date().isoformat():
            await _remind(bot, user, day, now)
    await service.check_finish(bot, uid)


async def tick(bot: Bot):
    now = service.now_local()
    for user in await db.list_active_users():
        try:
            await process_user(bot, user, now)
        except Exception:
            log.exception("Foydalanuvchi %s uchun xato", user["user_id"])


async def run(bot: Bot):
    while True:
        try:
            await tick(bot)
        except Exception:
            log.exception("Scheduler xatosi")
        await asyncio.sleep(config.TICK_SECONDS)
