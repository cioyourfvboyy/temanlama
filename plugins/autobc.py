"""
AutoBC Plugin
=============
Setiap postingan baru dari channel yang sudah didaftarkan via /autobc
akan otomatis di-broadcast ke seluruh user yang terdaftar di database.

Penggunaan:
  /autobc -1002628828282   → daftarkan channel (toggle on/off)
  /autobc list             → lihat daftar channel yang aktif
  /autobc off              → hapus semua channel (nonaktifkan semua)
"""

import asyncio
import contextlib
import time

from pyrogram.errors import FloodWait
from pyrogram.errors import RPCError
from pyrogram.errors import UserIsBlocked
from pyrogram.filters import channel
from pyrogram.filters import command
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from .helpers import decorator
from .helpers import helpers
from .helpers import make_progress_bar
from .helpers import make_status_text
from .helpers import Markup
from bot.client import Bot
from bot.utils.coloredkb import btn
from bot.utils.coloredkb import ckb
from bot.utils.coloredkb import edit_colored
from bot.utils.coloredkb import send_colored

CLOSE_MARKUP = ckb([[btn('Close', 'home-close', style='danger')]])


# ---------------------------------------------------------------------------
# Command handler: /autobc <channel_id | list | off>
# ---------------------------------------------------------------------------

@decorator.Admins
async def autobc_cmd(client: Bot, message: Message):
    """Tambah/hapus channel dari daftar AutoBC."""
    args = message.command[1:]  # semua argumen setelah /autobc

    # --- /autobc list ---
    if args and args[0].lower() == 'list':
        ids = await client.mdb.get_autobc()
        if not ids:
            return await message.reply(
                '📭 Belum ada channel yang didaftarkan AutoBC.',
                quote=True,
            )
        lines = '\n'.join(f'  • `{cid}`' for cid in ids)
        return await message.reply(
            f'📡 **Daftar Channel AutoBC:**\n{lines}',
            quote=True,
        )

    # --- /autobc off ---
    if args and args[0].lower() == 'off':
        ids = await client.mdb.get_autobc()
        for cid in ids:
            await client.mdb.del_autobc(cid)
        await client.var.fetching()
        await helpers.cached()  # FIX: reload() sync tidak isi ulang cacheids (invite link FSub), pakai cached() supaya tombol Join tidak hilang
        return await message.reply(
            '🛑 Semua AutoBC channel telah dinonaktifkan.',
            quote=True,
        )

    # --- /autobc <channel_id> ---
    if not args:
        return await message.reply(
            '⚠️ **Penggunaan:**\n'
            '`/autobc <channel_id>` — daftarkan/hapus channel\n'
            '`/autobc list` — lihat daftar channel aktif\n'
            '`/autobc off` — nonaktifkan semua',
            quote=True,
        )

    try:
        channel_id = int(args[0])
    except ValueError:
        return await message.reply(
            '❌ Channel ID tidak valid. Contoh: `/autobc -1002628828282`',
            quote=True,
        )

    # Cek apakah bot bisa mengakses channel tersebut
    try:
        chat = await client.get_chat(channel_id)
        chat_title = chat.title
    except RPCError:
        return await message.reply(
            f'❌ Tidak bisa mengakses channel `{channel_id}`.\n'
            'Pastikan bot sudah menjadi member/admin channel tersebut.',
            quote=True,
        )

    current_ids = await client.mdb.get_autobc()

    if channel_id in current_ids:
        # Toggle OFF → hapus
        await client.mdb.del_autobc(channel_id)
        await client.var.fetching()
        await helpers.cached()  # FIX: reload() sync tidak isi ulang cacheids (invite link FSub), pakai cached() supaya tombol Join tidak hilang
        await message.reply(
            f'🔕 AutoBC untuk channel **{chat_title}** (`{channel_id}`) '
            'telah **dinonaktifkan**.',
            quote=True,
        )
    else:
        # Toggle ON → tambah
        await client.mdb.add_autobc(channel_id)
        await client.var.fetching()
        await helpers.cached()  # FIX: reload() sync tidak isi ulang cacheids (invite link FSub), pakai cached() supaya tombol Join tidak hilang
        await message.reply(
            f'📡 AutoBC untuk channel **{chat_title}** (`{channel_id}`) '
            'telah **diaktifkan**.\n\n'
            'Setiap postingan baru di channel ini akan otomatis '
            'di-broadcast ke semua user.',
            quote=True,
        )


# ---------------------------------------------------------------------------
# Channel post handler: tangkap postingan baru dari channel terdaftar
# ---------------------------------------------------------------------------

async def autobc_handler(client: Bot, message: Message):
    """
    Dipanggil setiap ada postingan baru di channel manapun yang dipantau bot.
    Hanya diproses jika channel_id ada di daftar AUTOBC_IDS.
    Menampilkan progres broadcast secara real-time ke semua admin.
    """
    autobc_ids = await client.mdb.get_autobc()
    if not autobc_ids:
        return

    chat_id = message.chat.id
    if chat_id not in autobc_ids:
        return

    users = await client.mdb.gusrs()
    admns = helpers.adminids
    users = [usr for usr in users if usr not in admns]

    if not users:
        return

    total = len(users)
    sent = 0
    fail = 0
    running = True
    start_time = time.time()

    client.log.info(
        f'AutoBC: Postingan baru dari channel {chat_id}, '
        f'broadcast ke {total} user.'
    )

    _title = f'📡 **AutoBC dari channel `{chat_id}` sedang berjalan...**'

    # Kirim pesan status awal ke semua admin (chat_id, message_id) tuples
    status_msgs = []
    for admin_id in admns:
        with contextlib.suppress(RPCError):
            sm = await send_colored(
                client,
                admin_id,
                make_status_text(0, 0, total, title=_title),
                reply_markup=Markup.BROADCAST_STATS,
            )
            status_msgs.append((sm['chat']['id'], sm['message_id']))

    # Task update progres setiap 2 detik
    async def live_progress():
        while running:
            await asyncio.sleep(2)
            elapsed = time.time() - start_time
            for sm_chat_id, sm_msg_id in status_msgs:
                with contextlib.suppress(Exception):
                    await edit_colored(
                        client, sm_chat_id, sm_msg_id,
                        text=make_status_text(sent, fail, total, elapsed, title=_title),
                        reply_markup=Markup.BROADCAST_STATS,
                    )

    progress_task = asyncio.create_task(live_progress())

    for usr in users:
        try:
            await message.forward(usr, protect_content=helpers.protectc)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            with contextlib.suppress(RPCError):
                await message.forward(usr, protect_content=helpers.protectc)
                sent += 1
        except UserIsBlocked:
            await client.mdb.rmusr(usr)
            fail += 1
            client.log.info(f'AutoBC: User {usr} blocked bot, removed.')
        except RPCError as e:
            fail += 1
            client.log.warning(f'AutoBC: RPCError for user {usr}: {e}')

    # Hentikan task progres
    running = False
    progress_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await progress_task

    elapsed = time.time() - start_time
    bar, _ = make_progress_bar(sent, fail, total)

    # Hapus pesan status lama, kirim ringkasan akhir ke semua admin
    for sm_chat_id, sm_msg_id in status_msgs:
        with contextlib.suppress(RPCError):
            await client.delete_messages(sm_chat_id, sm_msg_id)
    for admin_id in admns:
        with contextlib.suppress(RPCError):
            await send_colored(
                client,
                admin_id,
                f'✅ **AutoBC Selesai!**\n\n'
                f'📡 Channel : `{chat_id}`\n'
                f'`{bar}`\n\n'
                f'✅ Terkirim  : `{sent}`\n'
                f'❌ Gagal     : `{fail}`\n'
                f'👥 Total     : `{total}`\n'
                f'🕐 Durasi    : `{elapsed:.0f}s`',
                reply_markup=CLOSE_MARKUP,
            )

    client.log.info(
        f'AutoBC selesai: {sent} terkirim, {fail} gagal '
        f'(channel: {chat_id})'
    )


# ---------------------------------------------------------------------------
# Register handlers
# ---------------------------------------------------------------------------

Bot.add_handler(
    MessageHandler(
        autobc_cmd,
        filters=command(Bot.cmd.autobc),
    ),
)

Bot.add_handler(
    MessageHandler(
        autobc_handler,
        filters=channel,
    ),
)
