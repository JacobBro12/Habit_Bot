import asyncio
import html
import logging
from io import BytesIO

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputMediaPhoto
from PIL import Image, ImageDraw, ImageFont

import brain
import config
import db
import plan

log = logging.getLogger(__name__)

STYLES = {
    "good": ("Bajarildi", (198, 239, 206)),
    "low": ("Qisman", (255, 235, 156)),
    "missed": ("Qilinmadi", (255, 199, 206)),
    "pending": ("Kutilmoqda", (238, 238, 238)),
    "active": ("Jarayonda", (221, 235, 247)),
}


def _font(size):
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _style(day):
    status = day["status"]
    if status == "done":
        return STYLES["good" if (day["score"] or 0) >= config.PASS_SCORE else "low"]
    if status == "missed":
        return STYLES["missed"]
    if status == "pending":
        return STYLES["pending"]
    return STYLES["active"]


def compute_stats(days):
    scores = [d["score"] for d in days if d["score"] is not None]
    passed = sum(1 for d in days if d["status"] == "done" and (d["score"] or 0) >= config.PASS_SCORE)
    total = len(days)
    return {
        "total": total,
        "passed": passed,
        "missed": sum(1 for d in days if d["status"] == "missed"),
        "finished": sum(1 for d in days if d["status"] in ("done", "missed")),
        "avg": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "percent": round(passed / total * 100) if total else 0,
    }


def render_table(user, days):
    width, row_h, top, header_h, foot_h = 1000, 42, 90, 48, 100
    height = top + header_h + row_h * len(days) + foot_h
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    f_title, f_head, f_row = _font(28), _font(20), _font(20)
    xs = [30, 110, 320, 640, 780]

    goal = user["goal"] if len(user["goal"]) <= 55 else user["goal"][:52] + "..."
    d.text((30, 28), f"Habit Tracker: {goal}", font=f_title, fill=(30, 30, 30), anchor="lm")
    d.text((30, 64), f"{plan.fmt_date(user['start_date'])} — {plan.fmt_date(user['end_date'])}", font=f_row, fill=(110, 110, 110), anchor="lm")

    d.rectangle([0, top, width, top + header_h], fill=(38, 70, 120))
    for x, label in zip(xs, ["№", "Sana", "Holat", "Ball", "Vaqt"]):
        d.text((x, top + header_h / 2), label, font=f_head, fill="white", anchor="lm")

    y = top + header_h
    for i, day in enumerate(days):
        if i % 2:
            d.rectangle([0, y, width, y + row_h], fill=(248, 248, 248))
        label, color = _style(day)
        d.rectangle([xs[2] - 12, y + 5, xs[3] - 30, y + row_h - 5], fill=color)
        mid = y + row_h / 2
        minutes = plan.total_minutes(plan.effective_tasks(day))
        score = f"{day['score']}/10" if day["score"] is not None else "-"
        d.text((xs[0], mid), str(day["idx"]), font=f_row, fill=(30, 30, 30), anchor="lm")
        d.text((xs[1], mid), plan.fmt_date(day["day"]), font=f_row, fill=(30, 30, 30), anchor="lm")
        d.text((xs[2], mid), label, font=f_row, fill=(30, 30, 30), anchor="lm")
        d.text((xs[3], mid), score, font=f_row, fill=(30, 30, 30), anchor="lm")
        d.text((xs[4], mid), f"{minutes} daq", font=f_row, fill=(30, 30, 30), anchor="lm")
        y += row_h

    stats = compute_stats(days)
    d.text((30, y + 28), f"Muvaffaqiyatli kunlar: {stats['passed']}/{stats['total']}   O'rtacha ball: {stats['avg']}/10", font=f_head, fill=(30, 30, 30), anchor="lm")
    bar_x, bar_w = 30, width - 60
    d.rounded_rectangle([bar_x, y + 58, bar_x + bar_w, y + 78], radius=10, fill=(230, 230, 230))
    filled = int(bar_w * stats["percent"] / 100)
    if filled > 0:
        d.rounded_rectangle([bar_x, y + 58, bar_x + max(filled, 20), y + 78], radius=10, fill=(56, 161, 105))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), height


async def send_table(bot: Bot, chat_id, user, days, caption=None):
    data, height = render_table(user, days)
    file = BufferedInputFile(data, filename="habit_tracker.png")
    if height > 3000:
        await bot.send_document(chat_id, file, caption=caption)
    else:
        await bot.send_photo(chat_id, file, caption=caption)


async def send_final(bot: Bot, user, days):
    chat_id = user["chat_id"]
    stats = compute_stats(days)
    header = (
        "🏁 <b>Maqsad kuni keldi!</b>\n\n"
        f"🎯 {html.escape(user['goal'])}\n"
        f"📅 {plan.fmt_date(user['start_date'])} — {plan.fmt_date(user['end_date'])}\n"
        f"✅ Muvaffaqiyatli kunlar: {stats['passed']}/{stats['total']}\n"
        f"⭐ O'rtacha ball: {stats['avg']}/10\n\n"
        "Mana bosib o'tgan yo'lingiz:"
    )
    await bot.send_message(chat_id, header)
    await send_table(bot, chat_id, user, days)

    lines = [
        f"Kun {d['idx']} ({d['day']}): {_style(d)[0]}, ball {d['score'] if d['score'] is not None else '-'}"
        for d in days
    ]
    try:
        summary = await brain.final_summary(user["goal"], stats, lines)
    except brain.BrainError:
        summary = (
            f"Siz {stats['total']} ish kunidan {stats['passed']} tasini yuqori ball bilan yakunladingiz. "
            f"O'rtacha ball: {stats['avg']}/10. Yangi maqsad qo'yish uchun /start yuboring."
        )
    await bot.send_message(chat_id, f"🧠 <b>Main Brain xulosasi</b>\n\n{html.escape(summary)}")

    sent_any = False
    for day in days:
        file_ids = (await db.get_photos(day["id"]))[: config.FINAL_PHOTOS_PER_DAY]
        if not file_ids:
            continue
        if not sent_any:
            await bot.send_message(chat_id, "📸 <b>Bajargan ishlaringiz rasmlari:</b>")
            sent_any = True
        caption = f"Kun {day['idx']} — {plan.fmt_date(day['day'])} — {day['score']}/10"
        try:
            if len(file_ids) == 1:
                await bot.send_photo(chat_id, file_ids[0], caption=caption)
            else:
                media = [
                    InputMediaPhoto(media=f, caption=caption if i == 0 else None)
                    for i, f in enumerate(file_ids)
                ]
                await bot.send_media_group(chat_id, media)
        except Exception:
            log.exception("Rasm yuborishda xato")
        await asyncio.sleep(0.6)

    await bot.send_message(chat_id, "Yangi maqsad qo'yish uchun /start yuboring. Omad! 🚀")
