import html
import json
import re
from datetime import date, timedelta

WEEK_PATTERNS = {1: [0], 3: [0, 2, 4], 7: [0, 1, 2, 3, 4, 5, 6]}
WEEK_LABELS = {1: "haftasiga 1 kun", 3: "haftasiga 3 kun", 7: "har kuni (haftasiga 7 kun)"}
MIN_DAILY = 10
MAX_DAILY = 960


def parse_minutes(text):
    t = text.lower().replace(",", ".")
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(?:soat|s\b|h\b)", t)
    mins = re.search(r"(\d+)\s*(?:daqiqa|daq|min|m\b|d\b)", t)
    total = 0.0
    if hours:
        total += float(hours.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    if not hours and not mins:
        plain = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", t)
        if plain:
            value = float(plain.group(1))
            total = value * 60 if value <= 16 else value
    return int(round(total))


def parse_time(text):
    m = re.fullmatch(r"\s*(\d{1,2})(?:\s*[:.]\s*(\d{2}))?\s*", text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def fmt_duration(minutes):
    hours, mins = divmod(int(minutes), 60)
    parts = []
    if hours:
        parts.append(f"{hours} soat")
    if mins:
        parts.append(f"{mins} daqiqa")
    return " ".join(parts) or "0 daqiqa"


def fmt_date(iso):
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def build_schedule(start, end, weekly_mode):
    offsets = WEEK_PATTERNS[weekly_mode]
    days = []
    cur = start
    while cur <= end:
        if (cur - start).days % 7 in offsets:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def effective_tasks(day):
    base = [
        {"name": t["name"], "minutes": int(t["minutes"]), "carried": False}
        for t in json.loads(day["tasks"])
    ]
    extra = [
        {"name": t["name"], "minutes": int(t["minutes"]), "carried": True}
        for t in json.loads(day["carry"])
    ]
    return base + extra


def total_minutes(tasks):
    return sum(t["minutes"] for t in tasks)


def format_tasks(tasks):
    lines = []
    for i, t in enumerate(tasks, 1):
        mark = " ♻️ <i>(kechagi qoldiq)</i>" if t.get("carried") else ""
        lines.append(f"{i}. {html.escape(t['name'])} — {fmt_duration(t['minutes'])}{mark}")
    return "\n".join(lines)


def merge_carry(existing, missed, cap):
    merged = {}
    for item in list(existing) + list(missed):
        merged[item["name"]] = merged.get(item["name"], 0) + int(item["minutes"])
    result = []
    used = 0
    for name, minutes in merged.items():
        room = cap - used
        if room <= 0:
            break
        value = min(minutes, room)
        result.append({"name": name, "minutes": value})
        used += value
    return result
