import json

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage

import db


def _key(key):
    return f"{key.chat_id}:{key.user_id}"


class PgStorage(BaseStorage):
    async def set_state(self, key, state=None):
        value = state.state if isinstance(state, State) else state
        await db.fsm_set_state(_key(key), value)

    async def get_state(self, key):
        return await db.fsm_get_state(_key(key))

    async def set_data(self, key, data):
        await db.fsm_set_data(_key(key), json.dumps(data, ensure_ascii=False))

    async def get_data(self, key):
        return json.loads(await db.fsm_get_data(_key(key)) or "{}")

    async def close(self):
        return None
