"""
plugins/info.py
================
Command /info — menampilkan kartu informasi bot dengan data:
  - Developer  -> diambil dari DB (DEV_USERNAME), default @Kyaa671
  - Bot Store  -> diambil dari DB (STORE_USERNAME), default @VIPXXXFSID

Developer & Bot Store bisa diubah owner/admin tanpa ubah kode, lewat:
  /setdev <username>    - atur username Developer
  /deldev                - hapus override, balik ke default
  /getdev                - cek username Developer aktif

  /setstore <username>  - atur username Bot Store
  /delstore              - hapus override, balik ke default
  /getstore              - cek username Bot Store aktif

Tombol pakai ikon emoji premium animasi (lihat PREMIUM_EMOJI_IDS di
bot/utils/coloredkb.py, key 'dev' & 'store'), otomatis fallback
ke emoji unicode biasa kalau ID belum/tidak terisi.
"""

from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from .helpers import decorator
from .helpers import helpers
from bot.client import Bot
from bot.utils.coloredkb import ckb
from bot.utils.coloredkb import pbtn
from bot.utils.coloredkb import premium_emoji
from bot.utils.coloredkb import send_colored


DEFAULT_DEV_USERNAME = 'Kyaa671'
DEFAULT_STORE_USERNAME = 'VIPXXXFSID'


async def _reload():
    """Sinkron ulang state Helpers dari DB, sama seperti pola di promo.py.

    FIX: helpers.reload() (sync) mengosongkan helpers.cacheids tanpa
    mengisi ulang invite link FSub (lihat catatan sama di promo.py).
    Ini KRITIS di file ini karena info() (handler /info, command PUBLIK,
    bisa dipanggil user manapun) sebelumnya memanggil helpers.reload()
    langsung setiap kali /info dijalankan -> begitu ada 1 user ketik
    /info, tombol Join FSub hilang untuk SEMUA user (cacheids adalah
    class-attribute, shared) sampai admin ubah FSUB_IDS atau bot
    restart -> user cuma lihat tombol "Try Again" tanpa tombol join
    sama sekali dan tidak pernah bisa lolos fsub. Sekarang pakai
    cached() yang generate ulang cacheids juga."""
    await helpers.cached()


async def info(client: Bot, message: Message):
    await _reload()
    dev_username = helpers.devusername or DEFAULT_DEV_USERNAME
    store_username = helpers.storeusername or DEFAULT_STORE_USERNAME

    header = f'{premium_emoji("info", "⚙️")} <b>Informasi Bot</b>'
    body = (
        '<b>Bot ini dikembangkan dan dikelola secara profesional.\n\n'
        '👨\u200d💻 Developer  : @' + dev_username + '\n'
        '🛒 Bot Store : @' + store_username + '</b>'
    )
    text = f'{header}\n\n{body}'

    markup = ckb([
        [
            pbtn('dev', 'Developer', url=f'https://t.me/{dev_username}', style='primary', fallback='🔔'),
        ],
        [
            pbtn('store', 'Bot Store', url=f'https://t.me/{store_username}', style='success', fallback='🔄'),
        ],
    ])

    await send_colored(
        client,
        message.chat.id,
        text,
        reply_markup=markup,
    )


# ---------------------------------------------------------------------------
# /setdev  /deldev  /getdev
# ---------------------------------------------------------------------------

@decorator.Admins
async def setdev(client: Bot, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            '<blockquote><b>👨\u200d💻 Kirimkan username Developer (tanpa @).\n\n'
            'Contoh:\n<code>/setdev allnakama</code></b></blockquote>',
        )
        return

    username = parts[1].strip().lstrip('@')
    await client.mdb.outvars('BOT_VARS', 'DEV_USERNAME')
    await client.mdb.invar('BOT_VARS', 'DEV_USERNAME', username)
    await client.var.fetching()
    await _reload()

    await message.reply(
        f'<blockquote><b>✅ Username Developer berhasil diatur ke:\n\n'
        f'@{username}</b></blockquote>',
    )


@decorator.Admins
async def deldev(client: Bot, message: Message):
    if not helpers.devusername:
        await message.reply(
            '<blockquote><b>ℹ️ Belum ada override username Developer, '
            f'masih pakai default @{DEFAULT_DEV_USERNAME}.</b></blockquote>',
        )
        return

    await client.mdb.outvars('BOT_VARS', 'DEV_USERNAME')
    await client.var.fetching()
    await _reload()

    await message.reply(
        f'<blockquote><b>🗑️ Override username Developer berhasil dihapus.\n\n'
        f'/info sekarang akan menampilkan default: @{DEFAULT_DEV_USERNAME}'
        '</b></blockquote>',
    )


@decorator.Admins
async def getdev(client: Bot, message: Message):
    username = helpers.devusername or DEFAULT_DEV_USERNAME
    await message.reply(
        f'<blockquote><b>👨\u200d💻 Username Developer aktif:\n\n'
        f'@{username}</b></blockquote>',
    )


# ---------------------------------------------------------------------------
# /setstore  /delstore  /getstore
# ---------------------------------------------------------------------------

@decorator.Admins
async def setstore(client: Bot, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            '<blockquote><b>🛒 Kirimkan username Bot Store (tanpa @).\n\n'
            'Contoh:\n<code>/setstore elzstore_id</code></b></blockquote>',
        )
        return

    username = parts[1].strip().lstrip('@')
    await client.mdb.outvars('BOT_VARS', 'STORE_USERNAME')
    await client.mdb.invar('BOT_VARS', 'STORE_USERNAME', username)
    await client.var.fetching()
    await _reload()

    await message.reply(
        f'<blockquote><b>✅ Username Bot Store berhasil diatur ke:\n\n'
        f'@{username}</b></blockquote>',
    )


@decorator.Admins
async def delstore(client: Bot, message: Message):
    if not helpers.storeusername:
        await message.reply(
            '<blockquote><b>ℹ️ Belum ada override username Bot Store, '
            f'masih pakai default @{DEFAULT_STORE_USERNAME}.</b></blockquote>',
        )
        return

    await client.mdb.outvars('BOT_VARS', 'STORE_USERNAME')
    await client.var.fetching()
    await _reload()

    await message.reply(
        f'<blockquote><b>🗑️ Override username Bot Store berhasil dihapus.\n\n'
        f'/info sekarang akan menampilkan default: @{DEFAULT_STORE_USERNAME}'
        '</b></blockquote>',
    )


@decorator.Admins
async def getstore(client: Bot, message: Message):
    username = helpers.storeusername or DEFAULT_STORE_USERNAME
    await message.reply(
        f'<blockquote><b>🛒 Username Bot Store aktif:\n\n'
        f'@{username}</b></blockquote>',
    )


Bot.add_handler(
    MessageHandler(
        info,
        filters=command(Bot.cmd.info) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        setdev,
        filters=command(Bot.cmd.setdev) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        deldev,
        filters=command(Bot.cmd.deldev) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        getdev,
        filters=command(Bot.cmd.getdev) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        setstore,
        filters=command(Bot.cmd.setstore) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        delstore,
        filters=command(Bot.cmd.delstore) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        getstore,
        filters=command(Bot.cmd.getstore) & private,
    ),
)
