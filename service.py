import asyncio
import html
import json
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import brain
import config
import db
import plan
import report

log = logging.getLogger(__name__)
esc = html.escape

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


def _retry_delay_minutes(attempts):
    idx = min(attempts - 1, len(config.EVAL_RETRY_MINUTES) - 1)
    return config.EVAL_RETRY_MINUTES[idx]


async def try_evaluate(bot: Bot, user, day, announce=None):
    day_id = day["id"]
    file_ids = await db.get_photos(day_id)
    tasks = plan.effective_tasks(day)
    photos = []
    for file_id in file_ids[: config.MAX_GEMINI_PHOTOS]:
        try:
            photos.append((await bot.download(file_id)).read())
        except Exception:
            log.exception("Rasm yuklab olinmadi (day_id=%s)", day_id)

    async def reply(text, markup=None):
        if announce:
            await announce.edit_text(text, reply_markup=markup)
        else:
            await bot.send_message(user["chat_id"], text, reply_markup=markup)

    try:
        result = await brain.evaluate_day(user["goal"], tasks, day["report_text"], photos, len(file_ids))
    except brain.BrainError as exc:
        attempts = day["eval_attempts"] + 1
        log.error("evaluate_day muvaffaqiyatsiz (day_id=%s, %s-urinish): %s", day_id, attempts, exc, exc_info=True)
        if attempts >= config.MAX_EVAL_RETRIES:
            await db.update_day(day_id, status="collecting_photos", eval_attempts=0, eval_next_at=None)
            await reply(
                "⚠️ Main Brain hozircha (Gemini serveri band) javob bera olmayapti. "
                "Rasmlaringiz va hisobotingiz saqlanib qoldi — birozdan so'ng «Tayyor» tugmasini qayta bosing.",
                kb([("✅ Tayyor", f"done:{day_id}")]),
            )
            return
        next_at = (now_local() + timedelta(minutes=_retry_delay_minutes(attempts))).isoformat()
        await db.update_day(day_id, status="collecting_photos", eval_attempts=attempts, eval_next_at=next_at)
        await reply(
            f"⚠️ Main Brain (Gemini) hozir band, {_retry_delay_minutes(attempts)} daqiqadan so'ng avtomatik "
            "qayta urinaman. Xohlasangiz «Tayyor» tugmasini bosib darhol qayta urinishingiz ham mumkin.",
            kb([("✅ Tayyor", f"done:{day_id}")]),
        )
        return

    score = result["score"]
    missed = [tasks[i - 1] for i in result["missed"]]
    if score < config.PASS_SCORE and not missed:
        missed = tasks
    done_names = [tasks[i - 1]["name"] for i in result["done"]]
    missed_items = [{"name": t["name"], "minutes": t["minutes"]} for t in missed]
    nxt = await close_day(user, day, score, result["feedback"], missed_items, "done")

    lines = [f"📊 <b>Bugungi baho: {score}/10</b>"]
    if done_names:
        lines.append("\n✅ <b>Bajarilgan:</b>\n" + "\n".join(f"• {esc(n)}" for n in done_names))
    if missed:
        lines.append("\n❌ <b>Bajarilmagan:</b>\n" + "\n".join(f"• {esc(t['name'])}" for t in missed))
    if result["feedback"]:
        lines.append(f"\n💬 {esc(result['feedback'])}")

    if score >= config.PASS_SCORE:
        upcoming = await db.get_next_pending_day(user["user_id"], day["day"])
        if upcoming:
            lines.append(f"\n🔥 Zo'r! Reja o'zgarishsiz davom etadi. Keyingi ish kuni: {plan.fmt_date(upcoming['day'])}.")
        else:
            lines.append("\n🔥 Zo'r! Bu oxirgi ish kuni edi.")
    elif nxt:
        lines.append(f"\n➕ Bajarilmagan vazifalar <b>{plan.fmt_date(nxt['day'])}</b> kungi rejaga qo'shildi.")
    else:
        lines.append("\nBu oxirgi ish kuni edi.")

    await reply("\n".join(lines))
    await check_finish(bot, user["user_id"])


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
