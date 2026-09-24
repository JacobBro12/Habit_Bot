import asyncpg

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    goal TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    daily_minutes INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    weekly_mode INTEGER NOT NULL,
    exercises TEXT NOT NULL,
    finished INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS days (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    day TEXT NOT NULL,
    idx INTEGER NOT NULL,
    tasks TEXT NOT NULL,
    carry TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    score INTEGER,
    report_text TEXT,
    feedback TEXT,
    started_at TEXT,
    due_at TEXT,
    reminders INTEGER NOT NULL DEFAULT 0,
    last_reminded_at TEXT,
    UNIQUE (user_id, day)
);
CREATE TABLE IF NOT EXISTS photos (
    id BIGSERIAL PRIMARY KEY,
    day_id BIGINT NOT NULL,
    file_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fsm (
    key TEXT PRIMARY KEY,
    state TEXT,
    data TEXT NOT NULL DEFAULT '{}'
);
"""

_pool = None


async def init():
    global _pool
    if not config.DATABASE_URL:
        raise SystemExit("DATABASE_URL to'ldirilishi kerak")
    _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    await _pool.execute(SCHEMA)
    await _pool.execute("UPDATE days SET status='collecting_photos' WHERE status='evaluating'")


async def close():
    if _pool:
        await _pool.close()


async def _one(sql, *args):
    row = await _pool.fetchrow(sql, *args)
    return dict(row) if row else None


async def _all(sql, *args):
    return [dict(r) for r in await _pool.fetch(sql, *args)]


async def get_user(user_id):
    return await _one("SELECT * FROM users WHERE user_id=$1", user_id)


async def create_user(user_id, chat_id, name, goal, start_date, end_date, daily_minutes, start_time, weekly_mode, exercises):
    await _pool.execute(
        "INSERT INTO users (user_id, chat_id, name, goal, start_date, end_date, daily_minutes, start_time, weekly_mode, exercises) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
        user_id, chat_id, name, goal, start_date, end_date, daily_minutes, start_time, weekly_mode, exercises,
    )


async def delete_user(user_id):
    await _pool.execute("DELETE FROM photos WHERE day_id IN (SELECT id FROM days WHERE user_id=$1)", user_id)
    await _pool.execute("DELETE FROM days WHERE user_id=$1", user_id)
    await _pool.execute("DELETE FROM users WHERE user_id=$1", user_id)


async def list_active_users():
    return await _all("SELECT * FROM users WHERE finished=0")


async def finish_user(user_id):
    await _pool.execute("UPDATE users SET finished=1 WHERE user_id=$1", user_id)


async def create_days(user_id, rows):
    await _pool.executemany(
        "INSERT INTO days (user_id, day, idx, tasks) VALUES ($1,$2,$3,$4)",
        [(user_id, day, idx, tasks) for day, idx, tasks in rows],
    )


async def get_day(day_id):
    return await _one("SELECT * FROM days WHERE id=$1", day_id)


async def get_day_by_date(user_id, day):
    return await _one("SELECT * FROM days WHERE user_id=$1 AND day=$2", user_id, day)


async def get_days(user_id):
    return await _all("SELECT * FROM days WHERE user_id=$1 ORDER BY day", user_id)


async def get_open_day(user_id):
    return await _one(
        "SELECT * FROM days WHERE user_id=$1 AND status IN ('awaiting_report','collecting_photos') "
        "ORDER BY day DESC LIMIT 1",
        user_id,
    )


async def get_next_pending_day(user_id, after_day):
    return await _one(
        "SELECT * FROM days WHERE user_id=$1 AND day>$2 AND status='pending' ORDER BY day LIMIT 1",
        user_id, after_day,
    )


async def update_day(day_id, **fields):
    cols = ", ".join(f"{k}=${i}" for i, k in enumerate(fields, 1))
    await _pool.execute(f"UPDATE days SET {cols} WHERE id=${len(fields) + 1}", *fields.values(), day_id)


async def add_photo(day_id, file_id):
    await _pool.execute("INSERT INTO photos (day_id, file_id) VALUES ($1,$2)", day_id, file_id)


async def get_photos(day_id):
    rows = await _all("SELECT file_id FROM photos WHERE day_id=$1 ORDER BY id", day_id)
    return [r["file_id"] for r in rows]


async def count_photos(day_id):
    row = await _one("SELECT COUNT(*) AS c FROM photos WHERE day_id=$1", day_id)
    return row["c"]


async def fsm_get_state(key):
    row = await _one("SELECT state FROM fsm WHERE key=$1", key)
    return row["state"] if row else None


async def fsm_set_state(key, state):
    await _pool.execute(
        "INSERT INTO fsm (key, state) VALUES ($1,$2) ON CONFLICT (key) DO UPDATE SET state=EXCLUDED.state",
        key, state,
    )


async def fsm_get_data(key):
    row = await _one("SELECT data FROM fsm WHERE key=$1", key)
    return row["data"] if row else "{}"


async def fsm_set_data(key, data):
    await _pool.execute(
        "INSERT INTO fsm (key, data) VALUES ($1,$2) ON CONFLICT (key) DO UPDATE SET data=EXCLUDED.data",
        key, data,
    )
