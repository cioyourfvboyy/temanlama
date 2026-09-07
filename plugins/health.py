"""
plugins/health.py
==================
Command /health — cek kesehatan bot secara menyeluruh (REAL, bukan simulasi
— tiap angka diambil langsung dari state bot/OS yang sedang berjalan) dan
kasih vonis apakah bot SIAP dipakai untuk broadcast massal atau TIDAK,
lengkap alasannya. Proses pengecekan ditampilkan LIVE lewat progress bar
(mirip gaya /bc), jadi user bisa lihat tahap mana yang sedang dicek.

Yang dicek (semua live, bukan angka statis):
  1. Ping ke Telegram (latency MTProto asli)
  2. Event-loop lag (delay asyncio.sleep(0) di loop yang sedang jalan)
  3. Koneksi SQLite (query asli ke DB)
  4. Jumlah user terdaftar (query asli ke tabel users)
  5. Status broadcast/autobc yang sedang berjalan (baca gVarBcRun asli)
  6. FSub channel/grup (baca cache invite-link asli hasil helpers.cached())
  7. Ruang disk kosong (shutil.disk_usage asli ke OS)
  8. Ukuran log.txt (os.path.getsize asli)
  9. RAM proses bot (resource.getrusage asli)
  10. Uptime bot (dihitung dari Bot.start_time asli)

Threshold di bawah ini (MAX_PING_OK_MS dkk) adalah patokan umum untuk VPS
kecil/menengah — boleh diubah manual sesuai kondisi server kamu.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import resource
import shutil
import time

from pyrogram.errors import RPCError
from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.handlers import MessageHandler
from pyrogram.raw.functions import Ping
from pyrogram.types import Message

from .helpers import decorator
from .helpers import helpers
from bot.client import Bot
from bot.utils.coloredkb import btn
from bot.utils.coloredkb import ckb
from bot.utils.coloredkb import edit_colored
from bot.utils.coloredkb import send_colored


CLOSE_MARKUP = ckb([[btn('Close', 'home-close', style='danger')]])

# ---------------------------------------------------------------------------
# Threshold — patokan umum VPS kecil/menengah, boleh diubah manual
# ---------------------------------------------------------------------------
MAX_PING_OK_MS = 500
MAX_LOOP_LAG_OK_MS = 300
MIN_FREE_DISK_MB = 300
MAX_LOG_SIZE_MB = 50


def _bar(done: int, total: int, length: int = 10) -> str:
    percent = (done / total * 100) if total else 100
    filled = int(done / total * length) if total else length
    return f"[{'█' * filled}{'░' * (length - filled)}] {percent:.0f}%"


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, seconds = divmod(seconds, 60)
    parts = []
    if d:
        parts.append(f'{d}h')
    if h:
        parts.append(f'{h}j')
    if m:
        parts.append(f'{m}m')
    parts.append(f'{seconds}d')
    return ' '.join(parts)


def mark(ok: bool) -> str:
    return '✅' if ok else '⚠️'


# ---------------------------------------------------------------------------
# Setiap step: (label untuk header progress, fungsi async yang return
# (baris_laporan: str, blocker: str|None, warning: str|None))
# blocker  -> alasan keras "TIDAK SIAP"
# warning  -> alasan "SIAP DENGAN CATATAN"
# ---------------------------------------------------------------------------

async def step_ping(client: Bot, ctx: dict):
    start = time.time()
    try:
        await client.invoke(Ping(ping_id=0))
        ms = (time.time() - start) * 1000
        ok = ms <= MAX_PING_OK_MS
        line = f'• Ping Telegram   : `{ms:.0f} ms` {mark(ok)}'
        warning = None if ok else f'Latency ke Telegram cukup tinggi ({ms:.0f} ms), broadcast bisa lebih lambat.'
        return line, None, warning
    except RPCError:
        return '• Ping Telegram   : ❌ Gagal terhubung', 'Bot tidak terhubung ke server Telegram.', None


async def step_looplag(client: Bot, ctx: dict):
    start = time.time()
    await asyncio.sleep(0)
    ms = (time.time() - start) * 1000
    ok = ms <= MAX_LOOP_LAG_OK_MS
    line = f'• Event Loop Lag  : `{ms:.1f} ms` {mark(ok)}'
    warning = None if ok else 'Event loop bot terdeteksi lag/berat — kemungkinan ada proses lain yang memblokir.'
    return line, None, warning


async def step_db(client: Bot, ctx: dict):
    try:
        await client.mdb.gvars('BOT_VARS')
        return '• SQLite Database : OK ✅', None, None
    except Exception:
        return '• SQLite Database : GAGAL ❌', 'Koneksi database (SQLite) gagal.', None


async def step_users(client: Bot, ctx: dict):
    users = await client.mdb.gusrs()
    total = len(users) if users else 0
    ctx['total_users'] = total
    blocker = 'Belum ada user terdaftar untuk di-broadcast.' if total == 0 else None
    return f'• User Terdaftar  : `{total}`', blocker, None


async def step_broadcast(client: Bot, ctx: dict):
    running = False
    try:
        from . import broadcast as broadcast_mod
        running = bool(getattr(broadcast_mod, 'gVarBcRun', False))
    except Exception:
        pass
    line = f'• Status Broadcast: {"SEDANG BERJALAN ⚠️" if running else "Idle ✅"}'
    blocker = 'Ada broadcast/autobc yang masih berjalan sekarang.' if running else None
    return line, blocker, None


async def step_fsub(client: Bot, ctx: dict):
    total = len(helpers.fsubcids)
    if total == 0:
        return '• FSub Channel    : tidak diset (opsional)', None, None
    valid = 0
    problems = []
    for i, cid in enumerate(helpers.fsubcids, start=1):
        entry = helpers.cacheids.get(cid)
        if entry and entry.get('ilink'):
            valid += 1
        else:
            problems.append(
                f'FSub #{i} (`{cid}`) bermasalah — invite link tidak valid. '
                'Kemungkinan bot bukan admin lagi, di-kick, atau di-ban dari '
                'channel/grup ini.',
            )
    line = f'• FSub Channel    : `{valid}/{total}` valid {mark(valid == total)}'
    warning = None
    if valid < total:
        warning = f'{total - valid} channel FSub bermasalah — sebagian user bisa gagal lolos force-join. ' + '; '.join(problems)
    return line, None, warning


async def step_disk(client: Bot, ctx: dict):
    try:
        usage = shutil.disk_usage('.')
        free_mb = usage.free / (1024 * 1024)
        ok = free_mb >= MIN_FREE_DISK_MB
        line = f'• Disk Kosong     : `{free_mb:.0f} MB` {mark(ok)}'
        warning = None if ok else f'Ruang disk tersisa cuma {free_mb:.0f} MB, rawan penuh/crash saat broadcast besar.'
        return line, None, warning
    except Exception:
        return '• Disk Kosong     : tidak bisa dicek ⚠️', None, None


async def step_log(client: Bot, ctx: dict):
    try:
        size_mb = os.path.getsize('log.txt') / (1024 * 1024)
    except FileNotFoundError:
        size_mb = 0.0
    ok = size_mb <= MAX_LOG_SIZE_MB
    line = f'• Ukuran log.txt  : `{size_mb:.1f} MB` {mark(ok)}'
    warning = None if ok else f'log.txt sudah {size_mb:.1f} MB, kemungkinan ada error berulang — cek /log sebelum broadcast besar.'
    return line, None, warning


async def step_ram(client: Bot, ctx: dict):
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mb = kb / 1024
    return f'• RAM Proses Bot  : `{mb:.1f} MB`', None, None


STEPS = [
    ('Ping Telegram', step_ping),
    ('Event Loop', step_looplag),
    ('Database', step_db),
    ('User Terdaftar', step_users),
    ('Status Broadcast', step_broadcast),
    ('FSub Channel', step_fsub),
    ('Disk Kosong', step_disk),
    ('Ukuran Log', step_log),
    ('RAM Proses', step_ram),
]


@decorator.Admins
async def health(client: Bot, message: Message):
    total_steps = len(STEPS)
    ctx: dict = {}
    lines: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []

    header = '<b>🩺 Mengecek Kondisi Bot...</b>'
    msg_data = await send_colored(
        client,
        message.chat.id,
        f'{header}\n`{_bar(0, total_steps)}` (0/{total_steps})\n\n⏳ Memulai pengecekan...',
    )
    chat_id = msg_data['chat']['id']
    msg_id = msg_data['message_id']

    for i, (label, fn) in enumerate(STEPS, start=1):
        try:
            line, blocker, warning = await fn(client, ctx)
        except Exception as e:
            line = f'• {label}: ❌ Error saat cek ({e})'
            blocker = None
            warning = f'Gagal mengecek {label}: {e}'
        lines.append(line)
        if blocker:
            blockers.append(blocker)
        if warning:
            warnings.append(warning)

        progress_text = (
            f'{header}\n`{_bar(i, total_steps)}` ({i}/{total_steps})\n'
            f'🔍 Cek: {label}...\n\n' + '\n'.join(lines)
        )
        with contextlib.suppress(RPCError):
            await edit_colored(client, chat_id, msg_id, text=progress_text)
        await asyncio.sleep(0.25)  # jeda kecil biar progres kelihatan jelas, bukan numpuk sekaligus

    uptime = time.time() - (client.start_time or time.time())
    total_users = ctx.get('total_users', 0)

    result_lines = ['<b>🩺 Laporan Kondisi Bot</b>\n']
    result_lines.extend(lines)
    result_lines.append(f'• Uptime          : `{_fmt_uptime(uptime)}`')

    result_lines.append('\n<b>━━━━━━━━━━━━━━━━━━</b>')
    if blockers:
        result_lines.append(f'<b>❌ TIDAK SIAP untuk broadcast massal ke {total_users} user.</b>')
        result_lines.append('\n<b>Penyebab:</b>')
        for b in blockers:
            result_lines.append(f'• {b}')
    elif warnings:
        result_lines.append(f'<b>⚠️ SIAP DENGAN CATATAN untuk broadcast ke {total_users} user.</b>')
        result_lines.append('\n<b>Perhatikan dulu:</b>')
        for w in warnings:
            result_lines.append(f'• {w}')
    else:
        result_lines.append(f'<b>✅ SIAP untuk broadcast massal ke {total_users} user.</b>')

    final_text = '\n'.join(result_lines)
    with contextlib.suppress(RPCError):
        await edit_colored(client, chat_id, msg_id, text=final_text, reply_markup=CLOSE_MARKUP)


Bot.add_handler(
    MessageHandler(
        health,
        filters=command(Bot.cmd.health) & private,
    ),
)
