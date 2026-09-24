import asyncio
import html
import json
import logging
from datetime import date, datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
import db
import plan
import report

log = logging.getLogger(__name__)

OPEN_STATUSES = ("pending", "running", "awaiting_report", "collecting_photos", "evaluating")

_finish_lock = asyncio.Lock()


def kb(*rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def now_local():
    return datetime.now(config.TZ).replace(tzinfo=None)


async def wipe_user(user_id):
    await db.delete_user(user_id)


async def ask_report(bot: Bot, day):
    user = await db.get_user(day["user_id"])
    if not user:
        return
    await db.update_day(day["id"], status="awaiting_report")
    tasks = plan.effective_tasks(day)
    text = (
        "⏰ <b>Vaqt tugadi!</b>\n\n"
        f"{html.escape(user['name'])}, bugungi vazifalarni bajardingizmi?\n\n"
        f"{plan.format_tasks(tasks)}\n\n"
        "Bitta xabarda yozing:\n"
        "• nimalarni bajardingiz\n"
        "• nimalarni bajarmadingiz\n"
        "• sabablari nima"
    )
    await bot.send_message(user["chat_id"], text)


async def close_day(user, day, score, feedback, missed_items, status):
    await db.update_day(day["id"], status=status, score=score, feedback=feedback)
    if score >= config.PASS_SCORE or not missed_items:
        return None
    nxt = await db.get_next_pending_day(user["user_id"], day["day"])
    if not nxt:
        return None
    carry = plan.merge_carry(json.loads(nxt["carry"]), missed_items, user["daily_minutes"])
    await db.update_day(nxt["id"], carry=json.dumps(carry, ensure_ascii=False))
    return nxt


async def roll_missed(bot: Bot, user, day, notify=True):
    tasks = plan.effective_tasks(day)
    missed = [{"name": t["name"], "minutes": t["minutes"]} for t in tasks]
    nxt = await close_day(user, day, 0, None, missed, "missed")
    if not notify:
        return
    text = f"⚠️ <b>{plan.fmt_date(day['day'])}</b> kungi vazifalar bajarilmadi (hisobot kelmadi). Ball: 0/10."
    if nxt:
        text += f"\nBajarilmaganlar <b>{plan.fmt_date(nxt['day'])}</b> kuniga qo'shildi."
    try:
        await bot.send_message(user["chat_id"], text, disable_notification=True)
    except Exception:
        log.exception("Xabar yuborilmadi")


async def check_finish(bot: Bot, user_id):
    async with _finish_lock:
        user = await db.get_user(user_id)
        if not user or user["finished"]:
            return
        today = now_local().date()
        end = date.fromisoformat(user["end_date"])
        if today < end:
            return
        days = await db.get_days(user_id)
        open_days = [d for d in days if d["status"] in OPEN_STATUSES]
        if today == end and open_days:
            return
        for d in open_days:
            fresh = await db.get_day(d["id"])
            await roll_missed(bot, user, fresh, notify=False)
        days = await db.get_days(user_id)
        try:
            await report.send_final(bot, user, days)
        except Exception:
            log.exception("Yakuniy hisobot yuborilmadi")
        await db.finish_user(user_id)
