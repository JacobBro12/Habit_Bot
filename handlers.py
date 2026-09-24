import html
import json
import logging
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import brain
import config
import db
import plan
import report
import service
from service import kb

log = logging.getLogger(__name__)
router = Router()
esc = html.escape
_last_group = {}

STATUS_TEXT = {
    "pending": "boshlanishi kutilmoqda",
    "running": "jarayonda",
    "awaiting_report": "hisobot kutilmoqda",
    "collecting_photos": "rasmlar kutilmoqda",
    "evaluating": "baholanmoqda",
    "done": "yakunlangan",
    "missed": "o'tkazib yuborilgan",
}


class Onboard(StatesGroup):
    goal = State()
    days_left = State()
    daily = State()
    exercises = State()
    start_time = State()
    weekly = State()


WELCOME = (
    "👋 Salom! Men <b>Main Brain</b> — sizning shaxsiy habit tracker botingizman.\n\n"
    "Maqsadingizni kunlarga bo'lib, har kuni eslataman, natijangizni baholayman va oxirida "
    "butun yo'lingizni jadval va rasmlar bilan taqdim etaman.\n\n"
    "Boshladik! 1/6\n"
    "🎯 <b>Maqsadingiz nima?</b> (masalan: IELTS 7.0 olish, 5 kg ozish, Python o'rganish)"
)

HELP = (
    "📖 <b>Buyruqlar</b>\n"
    "/start — yangi maqsad qo'yish\n"
    "/holat — bugungi holat va umumiy natija\n"
    "/jadval — habit tracker jadvali\n"
    "/reset — maqsadni o'chirib, qaytadan boshlash"
)


async def status_text(user):
    days = await db.get_days(user["user_id"])
    stats = report.compute_stats(days)
    today = service.now_local().date()
    left = max((date.fromisoformat(user["end_date"]) - today).days, 0)
    lines = [
        f"🎯 <b>{esc(user['goal'])}</b>",
        f"📅 Maqsad kuni: {plan.fmt_date(user['end_date'])} (qoldi: {left} kun)",
        f"✅ Muvaffaqiyatli kunlar: {stats['passed']}/{stats['total']}",
        f"⭐ O'rtacha ball: {stats['avg']}/10",
    ]
    today_day = next((d for d in days if d["day"] == today.isoformat()), None)
    if user["finished"]:
        lines.append("\n🏁 Maqsad yakunlangan. Yangisi uchun /start.")
    elif today_day:
        tasks = plan.effective_tasks(today_day)
        lines.append(f"\n<b>Bugun</b> ({STATUS_TEXT.get(today_day['status'], today_day['status'])}):")
        lines.append(plan.format_tasks(tasks))
    else:
        lines.append("\n😌 Bugun ish kuni emas.")
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(m.from_user.id)
    if user and not user["finished"]:
        await m.answer("Sizda faol maqsad bor:\n\n" + await status_text(user) + "\n\nYangidan boshlash uchun /reset.")
        return
    await state.set_state(Onboard.goal)
    await m.answer(WELCOME)


@router.message(Command("yordam", "help"))
async def cmd_help(m: Message):
    await m.answer(HELP)


@router.message(Command("holat"))
async def cmd_status(m: Message):
    user = await db.get_user(m.from_user.id)
    if not user:
        await m.answer("Hali maqsad yo'q. Boshlash uchun /start.")
        return
    await m.answer(await status_text(user))


@router.message(Command("jadval"))
async def cmd_table(m: Message, bot: Bot):
    user = await db.get_user(m.from_user.id)
    if not user:
        await m.answer("Hali maqsad yo'q. Boshlash uchun /start.")
        return
    days = await db.get_days(user["user_id"])
    await report.send_table(bot, m.chat.id, user, days)


@router.message(Command("reset"))
async def cmd_reset(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "⚠️ Barcha ma'lumotlar va saqlangan rasmlar o'chadi. Davom etamizmi?",
        reply_markup=kb([("Ha, o'chirish", "reset:yes"), ("Bekor qilish", "reset:no")]),
    )


@router.callback_query(F.data.startswith("reset:"))
async def cb_reset(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    if cb.data.endswith("yes"):
        await service.wipe_user(cb.from_user.id)
        await state.set_state(Onboard.goal)
        await cb.message.answer("🗑 O'chirildi.\n\n" + WELCOME)
    else:
        await cb.message.answer("Bekor qilindi.")


@router.message(Onboard.goal, F.text)
async def on_goal(m: Message, state: FSMContext):
    goal = m.text.strip()
    if not 3 <= len(goal) <= 200:
        await m.answer("Maqsadni 3 dan 200 belgigacha aniq yozing.")
        return
    await state.update_data(goal=goal)
    await state.set_state(Onboard.days_left)
    await m.answer("2/6\n📅 <b>Maqsad kunigacha necha kun qoldi?</b> (masalan: 30)")


@router.message(Onboard.days_left, F.text)
async def on_days_left(m: Message, state: FSMContext):
    text = m.text.strip()
    if not text.isdigit() or not 1 <= int(text) <= 365:
        await m.answer("1 dan 365 gacha butun son yozing.")
        return
    await state.update_data(days_left=int(text))
    await state.set_state(Onboard.daily)
    await m.answer("3/6\n⏳ <b>Kuniga qancha vaqt ajratasiz?</b> (masalan: 2 soat, 90 daqiqa, 1 soat 30 daqiqa)")


@router.message(Onboard.daily, F.text)
async def on_daily(m: Message, state: FSMContext):
    minutes = plan.parse_minutes(m.text)
    if not plan.MIN_DAILY <= minutes <= plan.MAX_DAILY:
        await m.answer("Vaqtni 10 daqiqadan 16 soatgacha oralig'ida yozing. Masalan: 2 soat yoki 45 daqiqa.")
        return
    await state.update_data(daily=minutes)
    await state.set_state(Onboard.exercises)
    await m.answer(
        f"Kunlik vaqt: <b>{plan.fmt_duration(minutes)}</b>\n\n"
        "4/6\n🏋️ <b>Qaysi mashqlarni qilasiz va har biriga qancha vaqt ajratasiz?</b>\n"
        "Har qatorga bittadan yozing:\n<code>Listening - 40 daqiqa\nSpeaking - 30 daqiqa</code>\n\n"
        "Yoki Main Brain o'zi tanlab bersin:",
        reply_markup=kb([("🧠 Brain tanlasin", "auto_ex")]),
    )


async def build_exercises(target: Message, state: FSMContext, raw):
    data = await state.get_data()
    wait = await target.answer("🧠 Main Brain mashqlar rejasini tuzmoqda...")
    try:
        exercises = await brain.build_exercises(data["goal"], data["daily"], raw)
    except brain.BrainError:
        await wait.edit_text("⚠️ Main Brain hozir javob bera olmadi. Mashqlarni qayta yuboring yoki tugmani qayta bosing.")
        return
    await state.update_data(exercises=exercises)
    await state.set_state(Onboard.start_time)
    tasks = [{"name": e["name"], "minutes": e["minutes"]} for e in exercises]
    await wait.edit_text(
        f"✅ <b>Kunlik mashqlar</b> (jami {plan.fmt_duration(plan.total_minutes(tasks))}):\n"
        f"{plan.format_tasks(tasks)}\n\n"
        "5/6\n⏰ <b>Kuniga soat nechada boshlash sizga qulay?</b> (masalan: 06:30 yoki 19:00)"
    )


@router.message(Onboard.exercises, F.text)
async def on_exercises(m: Message, state: FSMContext):
    if len(m.text.strip()) < 3:
        await m.answer("Mashqlarni yozing yoki «Brain tanlasin» tugmasini bosing.")
        return
    await build_exercises(m, state, m.text)


@router.callback_query(Onboard.exercises, F.data == "auto_ex")
async def on_auto_exercises(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await build_exercises(cb.message, state, "")


@router.message(Onboard.start_time, F.text)
async def on_start_time(m: Message, state: FSMContext):
    value = plan.parse_time(m.text)
    if not value:
        await m.answer("Vaqtni SS:DD shaklida yozing. Masalan: 06:30 yoki 19:00.")
        return
    await state.update_data(start_time=value)
    await state.set_state(Onboard.weekly)
    await m.answer(
        "6/6\n📆 <b>Haftasiga necha kun shug'ullanasiz?</b>",
        reply_markup=kb(
            [("1 kun", "wk:1"), ("3 kun", "wk:3"), ("7 kun", "wk:7")],
        ),
    )


@router.message(Onboard.weekly, F.text)
async def on_weekly_text(m: Message):
    await m.answer("Iltimos, yuqoridagi tugmalardan birini tanlang.")


@router.callback_query(Onboard.weekly, F.data.startswith("wk:"))
async def on_weekly(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    mode = int(cb.data.split(":")[1])
    data = await state.get_data()
    user_id = cb.from_user.id

    now = service.now_local()
    hour, minute = map(int, data["start_time"].split(":"))
    today = now.date()
    start = today if (now.hour, now.minute) < (hour, minute) else today + timedelta(days=1)
    end = today + timedelta(days=data["days_left"])
    schedule = plan.build_schedule(start, end, mode)
    if not schedule:
        await cb.message.answer("⚠️ Bu sozlamalarda ish kuni chiqmadi. /start bilan qayta urinib ko'ring.")
        await state.clear()
        return

    tasks_json = json.dumps(data["exercises"], ensure_ascii=False)
    await service.wipe_user(user_id)
    await db.create_user(
        user_id,
        cb.message.chat.id,
        cb.from_user.first_name or "Do'st",
        data["goal"],
        start.isoformat(),
        end.isoformat(),
        data["daily"],
        data["start_time"],
        mode,
        tasks_json,
    )
    await db.create_days(user_id, [(d.isoformat(), i, tasks_json) for i, d in enumerate(schedule, 1)])
    await state.clear()

    tasks = [{"name": e["name"], "minutes": e["minutes"]} for e in data["exercises"]]
    await cb.message.answer(
        "🎉 <b>Habit Tracker tayyor!</b>\n\n"
        f"🎯 {esc(data['goal'])}\n"
        f"📅 {plan.fmt_date(start.isoformat())} — {plan.fmt_date(end.isoformat())}\n"
        f"📆 Rejim: {plan.WEEK_LABELS[mode]}, jami ish kunlari: {len(schedule)}\n"
        f"⏰ Har kuni soat {data['start_time']}da eslataman\n\n"
        f"<b>Kunlik mashqlar:</b>\n{plan.format_tasks(tasks)}\n\n"
        f"Birinchi ish kuni: <b>{plan.fmt_date(schedule[0].isoformat())}</b>.\n"
        "Jadvalni ko'rish: /jadval, holat: /holat."
    )


@router.callback_query(F.data.startswith("start:"))
async def cb_begin(cb: CallbackQuery):
    day = await db.get_day(int(cb.data.split(":")[1]))
    if not day or day["user_id"] != cb.from_user.id or day["status"] != "pending":
        await cb.answer("Bu kun allaqachon boshlangan yoki yopilgan.", show_alert=True)
        return
    await cb.answer()
    now = service.now_local()
    minutes = plan.total_minutes(plan.effective_tasks(day))
    due = now + timedelta(minutes=minutes)
    await db.update_day(day["id"], status="running", started_at=now.isoformat(), due_at=due.isoformat())
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        f"🚀 <b>Boshlandi!</b> Vaqt hisoblanmoqda: {plan.fmt_duration(minutes)}.\n"
        f"Soat <b>{due.strftime('%H:%M')}</b>da hisobot so'rayman. Omad!",
        reply_markup=kb([("🏁 Erta tugatdim", f"early:{day['id']}")]),
    )


@router.callback_query(F.data.startswith("early:"))
async def cb_early(cb: CallbackQuery, bot: Bot):
    day = await db.get_day(int(cb.data.split(":")[1]))
    if not day or day["user_id"] != cb.from_user.id or day["status"] != "running":
        await cb.answer("Bu allaqachon yopilgan.", show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await service.ask_report(bot, day)


@router.callback_query(F.data.startswith("done:"))
async def cb_done(cb: CallbackQuery, bot: Bot):
    day_id = int(cb.data.split(":")[1])
    day = await db.get_day(day_id)
    if not day or day["user_id"] != cb.from_user.id or day["status"] != "collecting_photos":
        await cb.answer("Bu hisobot allaqachon yopilgan.", show_alert=True)
        return
    file_ids = await db.get_photos(day_id)
    if not file_ids:
        await cb.answer("Kamida 1 ta rasm yuboring.", show_alert=True)
        return
    await cb.answer()
    await db.update_day(day_id, status="evaluating")
    await cb.message.edit_reply_markup(reply_markup=None)
    wait = await cb.message.answer("🧠 Main Brain natijani baholayapti...")

    user = await db.get_user(cb.from_user.id)
    tasks = plan.effective_tasks(day)
    photos = []
    for file_id in file_ids[: config.MAX_GEMINI_PHOTOS]:
        try:
            photos.append((await bot.download(file_id)).read())
        except Exception:
            log.exception("Rasm yuklab olinmadi")
    try:
        result = await brain.evaluate_day(user["goal"], tasks, day["report_text"], photos, len(file_ids))
    except brain.BrainError:
        await db.update_day(day_id, status="collecting_photos")
        await wait.edit_text(
            "⚠️ Main Brain hozir javob bera olmadi. Birozdan so'ng «Tayyor» tugmasini qayta bosing.",
            reply_markup=kb([("✅ Tayyor", f"done:{day_id}")]),
        )
        return

    score = result["score"]
    missed = [tasks[i - 1] for i in result["missed"]]
    if score < config.PASS_SCORE and not missed:
        missed = tasks
    done_names = [tasks[i - 1]["name"] for i in result["done"]]
    missed_items = [{"name": t["name"], "minutes": t["minutes"]} for t in missed]
    nxt = await service.close_day(user, day, score, result["feedback"], missed_items, "done")

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

    await wait.edit_text("\n".join(lines))
    await service.check_finish(bot, user["user_id"])


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def on_text(m: Message):
    day = await db.get_open_day(m.from_user.id)
    if not day:
        await m.answer("Hozir hisobot kutilmayapti. Holatni ko'rish: /holat")
        return
    if day["status"] == "collecting_photos":
        await m.answer(
            "📸 Endi natija rasmlarini yuboring yoki tugagan bo'lsa «Tayyor» tugmasini bosing.",
            reply_markup=kb([("✅ Tayyor", f"done:{day['id']}")]),
        )
        return
    text = m.text.strip()
    if len(text) < 15:
        await m.answer("Hisobot juda qisqa. Nimalarni bajardingiz, nimalarni bajarmadingiz va sabablari nima? Batafsil yozing.")
        return
    await db.update_day(day["id"], report_text=text, status="collecting_photos")
    await m.answer(
        f"📸 Qabul qilindi. Endi natijangizning <b>1 dan {config.MAX_PHOTOS_PER_DAY} tagacha rasmini</b> yuboring "
        "(oddiy rasm sifatida, fayl emas).\nBarchasini yuborib bo'lgach «Tayyor» tugmasini bosing.",
        reply_markup=kb([("✅ Tayyor", f"done:{day['id']}")]),
    )


@router.message(StateFilter(None), F.photo)
async def on_photo(m: Message, bot: Bot):
    uid = m.from_user.id
    day = await db.get_open_day(uid)
    if not day:
        await m.answer("Hozir rasm kutilmayapti.")
        return
    if day["status"] == "awaiting_report":
        await m.answer("Avval matnli hisobot yozing: nimalarni bajardingiz, nimalarni yo'q va sabablari.")
        return
    count = await db.count_photos(day["id"])
    if count >= config.MAX_PHOTOS_PER_DAY:
        await m.answer(
            f"Maksimal {config.MAX_PHOTOS_PER_DAY} ta rasm qabul qilinadi. «Tayyor» tugmasini bosing.",
            reply_markup=kb([("✅ Tayyor", f"done:{day['id']}")]),
        )
        return
    await db.add_photo(day["id"], m.photo[-1].file_id)
    group = m.media_group_id
    if group and _last_group.get(uid) == group:
        return
    _last_group[uid] = group
    await m.answer(
        f"📸 Rasm qabul qilindi ({count + 1}/{config.MAX_PHOTOS_PER_DAY}). Yana yuboring yoki «Tayyor» ni bosing.",
        reply_markup=kb([("✅ Tayyor", f"done:{day['id']}")]),
    )
