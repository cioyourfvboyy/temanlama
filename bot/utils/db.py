"""
Database layer — aiosqlite (menggantikan MongoDB/motor).

Skema tabel:
  bvars  : key TEXT PK, field TEXT, value TEXT
  users  : id INTEGER PK
  rstrt  : id TEXT PK, cid INTEGER, mid INTEGER
"""
from __future__ import annotations

import json
import os
import aiosqlite

from config import Config

_DB_PATH = Config.DB_PATH


def _db() -> aiosqlite.Connection:
    """Return aiosqlite async context manager."""
    os.makedirs(os.path.dirname(_DB_PATH) if os.path.dirname(_DB_PATH) else '.', exist_ok=True)
    return aiosqlite.connect(_DB_PATH)


async def _setup(db: aiosqlite.Connection) -> None:
    db.row_factory = aiosqlite.Row
    await db.execute('PRAGMA journal_mode=WAL')
    await db.execute('PRAGMA synchronous=NORMAL')


class Database:
    """Async SQLite wrapper dengan API setara motor lama."""

    # -----------------------------------------------------------------------
    # Inisialisasi tabel
    # -----------------------------------------------------------------------
    async def init(self) -> None:
        async with _db() as db:
            await _setup(db)
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS bvars (
                    key   TEXT NOT NULL,
                    field TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (key, field, value)
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS rstrt (
                    id  TEXT PRIMARY KEY,
                    cid INTEGER NOT NULL,
                    mid INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quota (
                    user_id INTEGER NOT NULL,
                    day     TEXT    NOT NULL,
                    count   INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, day)
                );
            """)
            await db.commit()

    # -----------------------------------------------------------------------
    # bvars helpers (mirip MongoDB $addToSet / $pull / $unset)
    # -----------------------------------------------------------------------
    async def gvars(self, _id: str) -> dict | None:
        """Kembalikan seluruh field untuk key _id sebagai dict list."""
        async with _db() as db:
            await _setup(db)
            async with db.execute(
                'SELECT field, value FROM bvars WHERE key = ?', (_id,)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            return None
        result: dict[str, list] = {}
        for row in rows:
            field, raw = row['field'], row['value']
            val = json.loads(raw)
            result.setdefault(field, [])
            result[field].append(val)
        return result

    async def invar(self, _id: str, field: str, value) -> None:
        """$addToSet: insert jika belum ada (upsert)."""
        raw = json.dumps(value)
        async with _db() as db:
            await _setup(db)
            await db.execute(
                'INSERT OR IGNORE INTO bvars (key, field, value) VALUES (?, ?, ?)',
                (_id, field, raw),
            )
            await db.commit()

    async def rmvar(self, _id: str, field: str, value) -> None:
        """$pull: hapus satu nilai dari field."""
        raw = json.dumps(value)
        async with _db() as db:
            await _setup(db)
            await db.execute(
                'DELETE FROM bvars WHERE key = ? AND field = ? AND value = ?',
                (_id, field, raw),
            )
            await db.commit()

    async def outvars(self, _id: str, field: str) -> None:
        """$unset: hapus seluruh entri field untuk key."""
        async with _db() as db:
            await _setup(db)
            await db.execute(
                'DELETE FROM bvars WHERE key = ? AND field = ?',
                (_id, field),
            )
            await db.commit()

    # -----------------------------------------------------------------------
    # users
    # -----------------------------------------------------------------------
    async def gusrs(self) -> list[int]:
        async with _db() as db:
            await _setup(db)
            async with db.execute('SELECT id FROM users') as cur:
                rows = await cur.fetchall()
        return [r['id'] for r in rows]

    async def inusr(self, user: int) -> None:
        async with _db() as db:
            await _setup(db)
            await db.execute(
                'INSERT OR IGNORE INTO users (id) VALUES (?)', (user,)
            )
            await db.commit()

    async def rmusr(self, user: int) -> None:
        async with _db() as db:
            await _setup(db)
            await db.execute('DELETE FROM users WHERE id = ?', (user,))
            await db.commit()

    # -----------------------------------------------------------------------
    # rstrt (restart / broadcast pending message)
    # -----------------------------------------------------------------------
    async def inmsg(self, msg: str, cid: int, mid: int) -> None:
        async with _db() as db:
            await _setup(db)
            await db.execute(
                'INSERT OR REPLACE INTO rstrt (id, cid, mid) VALUES (?, ?, ?)',
                (msg, cid, mid),
            )
            await db.commit()

    async def gmsgs(self, msg: str) -> dict | None:
        async with _db() as db:
            await _setup(db)
            async with db.execute(
                'SELECT cid, mid FROM rstrt WHERE id = ?', (msg,)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return {'cid': row['cid'], 'mid': row['mid']}

    async def rmmsg(self, msg: str) -> None:
        async with _db() as db:
            await _setup(db)
            await db.execute('DELETE FROM rstrt WHERE id = ?', (msg,))
            await db.commit()

    # -----------------------------------------------------------------------
    # AutoBC helpers
    # -----------------------------------------------------------------------
    async def add_autobc(self, channel_id: int) -> None:
        await self.invar('BOT_VARS', 'AUTOBC_IDS', channel_id)

    async def del_autobc(self, channel_id: int) -> None:
        await self.rmvar('BOT_VARS', 'AUTOBC_IDS', channel_id)

    async def get_autobc(self) -> list[int]:
        doc = await self.gvars('BOT_VARS')
        if doc:
            return doc.get('AUTOBC_IDS', [])
        return []

    # -----------------------------------------------------------------------
    # Kuota harian per-member (fitur "kuota habis -> order VIP")
    # -----------------------------------------------------------------------
    async def get_quota(self, user_id: int, day: str) -> int:
        async with _db() as db:
            await _setup(db)
            async with db.execute(
                'SELECT count FROM quota WHERE user_id = ? AND day = ?',
                (user_id, day),
            ) as cur:
                row = await cur.fetchone()
        return row['count'] if row else 0

    async def bump_quota(self, user_id: int, day: str) -> int:
        """Naikkan counter kuota user untuk hari ini sebanyak 1, kembalikan
        nilai counter yang baru."""
        async with _db() as db:
            await _setup(db)
            await db.execute(
                'INSERT INTO quota (user_id, day, count) VALUES (?, ?, 1) '
                'ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1',
                (user_id, day),
            )
            await db.commit()
            async with db.execute(
                'SELECT count FROM quota WHERE user_id = ? AND day = ?',
                (user_id, day),
            ) as cur:
                row = await cur.fetchone()
        return row['count'] if row else 1


Database = Database()
