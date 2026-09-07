"""
plugins/promo.py
=================
Porting fitur dari fsub2 (logika/pendekatan sama, disesuaikan ke arsitektur
single-bot fsubcolorsingle — tanpa konsep multi-clone/bot_id, dan pakai
penyimpanan BOT_VARS yang sudah ada di project ini):

  /setcaption  - set teks caption otomatis di bawah konten
  /delcaption  - hapus caption otomatis
  /getcaption  - cek caption otomatis yang aktif

  /setpromo    - set link tombol 🌟 PROMO VIP di konten
  /delpromo    - hapus link tombol PROMO VIP
  /getpromo    - cek link PROMO VIP aktif

  /autodelete on <menit> | off | (tanpa argumen = cek status)
               - atur auto-delete konten yang dikirim ke member

Penyimpanan & penerapan efek (caption/promo/autodelete) sudah ditangani di
plugins/helpers.py (Helpers.build_caption / Helpers.promo_markup /
Helpers.schedule_autodelete) dan dipakai otomatis oleh Helpers.copymsgs()
saat bot mengirim konten — tidak ada perubahan pada plugin lain selain itu.
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
from bot.utils.coloredkb import send_colored


async def _reload():
    """Sinkron ulang state Helpers (helpers.captiontext / promolink /
    autodelete_raw) dari DB, sama seperti pola replace() di configs.py.

    FIX: dulu pakai helpers.reload() (sync) yang cuma narik ulang variabel
    dari DB TAPI mengosongkan helpers.cacheids tanpa mengisi ulang invite
    link-nya (reload() cuma manggil initializing(), bukan cached()).
    Akibatnya tombol Join FSub hilang total (cuma tombol Try Again yang
    muncul) begitu command di file ini dipanggil, sampai admin ubah
    FSUB_IDS lewat /set atau bot di-restart. Sekarang pakai cached() yang
    juga generate ulang cacheids (title + invite link) tiap FSub channel."""
    await helpers.cached()


# ---------------------------------------------------------------------------
# /setcaption  /delcaption  /getcaption
# ---------------------------------------------------------------------------

@decorator.Admins
async def setcaption(client: Bot, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            '<blockquote><b>📝 Kirimkan teks caption yang ingin ditampilkan '
            'otomatis di bawah setiap konten.\n\n'
            'Contoh:\n<code>/setcaption Terima kasih sudah join!</code></b></blockquote>',
        )
        return

    caption_text = parts[1].strip()
    await client.mdb.outvars('BOT_VARS', 'CAPTION_TEXT')
    await client.mdb.invar('BOT_VARS', 'CAPTION_TEXT', caption_text)
    await client.var.fetching()
    await _reload()

    await message.reply(
        f'<blockquote><b>✅ Caption otomatis berhasil diatur ke:\n\n'
        f'<code>{caption_text}</code>\n\n'
        f'Caption akan otomatis muncul di bawah setiap konten '
        f'yang dikirim bot ke member.</b></blockquote>',
    )


@decorator.Admins
async def delcaption(client: Bot, message: Message):
    if not helpers.captiontext:
        await message.reply(
            '<blockquote><b>ℹ️ Belum ada caption otomatis yang diset.</b></blockquote>',
        )
        return

    await client.mdb.outvars('BOT_VARS', 'CAPTION_TEXT')
    await client.var.fetching()
    await _reload()

    await message.reply(
        '<blockquote><b>🗑️ Caption otomatis berhasil dihapus.\n\n'
        'Konten yang dikirim bot tidak akan menyertakan caption tambahan.'
        '</b></blockquote>',
    )


@decorator.Admins
async def getcaption(client: Bot, message: Message):
    if not helpers.captiontext:
        await message.reply(
            '<blockquote><b>ℹ️ Belum ada caption otomatis yang diset.\n\n'
            'Gunakan /setcaption untuk mengaturnya.</b></blockquote>',
        )
        return

    await message.reply(
        f'<blockquote><b>📝 Caption otomatis aktif:\n\n'
        f'<code>{helpers.captiontext}</code></b></blockquote>',
    )


# ---------------------------------------------------------------------------
# /setpromo  /delpromo  /getpromo
# ---------------------------------------------------------------------------

@decorator.Admins
async def setpromo(client: Bot, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            '<blockquote><b>🔗 Kirimkan link untuk tombol PROMO VIP.\n\n'
            'Contoh:\n<code>/setpromo https://t.me/elzstore_id</code></b></blockquote>',
        )
        return

    link = parts[1].strip()
    if not link.startswith('http'):
        await message.reply(
            '<blockquote><b>❌ Link tidak valid. Pastikan dimulai dengan '
            'https:// atau http://</b></blockquote>',
        )
        return

    await client.mdb.outvars('BOT_VARS', 'PROMO_LINK')
    await client.mdb.invar('BOT_VARS', 'PROMO_LINK', link)
    await client.var.fetching()
    await _reload()

    await message.reply(
        f'<blockquote><b>✅ Link PROMO VIP berhasil diatur ke:\n\n'
        f'<code>{link}</code>\n\n'
        f'Tombol 🌟 PROMO VIP akan otomatis muncul di setiap konten '
        f'yang dikirim bot ke member.</b></blockquote>',
    )


@decorator.Admins
async def delpromo(client: Bot, message: Message):
    if not helpers.promolink:
        await message.reply(
            '<blockquote><b>ℹ️ Belum ada link PROMO VIP yang diset.</b></blockquote>',
        )
        return

    await client.mdb.outvars('BOT_VARS', 'PROMO_LINK')
    await client.var.fetching()
    await _reload()

    await message.reply(
        '<blockquote><b>🗑️ Link PROMO VIP berhasil dihapus.\n\n'
        'Tombol tidak akan muncul lagi di konten yang dikirim bot.</b></blockquote>',
    )


@decorator.Admins
async def getpromo(client: Bot, message: Message):
    if not helpers.promolink:
        await message.reply(
            '<blockquote><b>ℹ️ Belum ada link PROMO VIP yang diset.\n\n'
            'Gunakan /setpromo untuk mengaturnya.</b></blockquote>',
        )
        return

    markup = ckb([[pbtn('join', 'Preview Tombol', url=helpers.promolink, style='danger', fallback='🌟')]])
    await send_colored(
        client,
        message.chat.id,
        f'<blockquote><b>🌟 Link PROMO VIP aktif:\n\n'
        f'<code>{helpers.promolink}</code></b></blockquote>',
        reply_markup=markup,
    )


# ---------------------------------------------------------------------------
# /autodelete on <menit> | off | (tanpa argumen)
# ---------------------------------------------------------------------------

@decorator.Admins
async def autodelete_cmd(client: Bot, message: Message):
    args = message.command[1:]

    if not args:
        delay = helpers.get_autodelete_delay()
        if delay is None:
            await message.reply(
                '🔴 <b>Auto-delete saat ini: <u>OFF</u></b>\n\n'
                'Aktifkan dengan:\n<code>/autodelete on &lt;menit&gt;</code>',
            )
            return
        menit = delay // 60
        await message.reply(
            f'🟢 <b>Auto-delete saat ini: <u>ON</u></b>\n'
            f'⏱ Durasi: <b>{menit} menit</b>\n\n'
            f'Matikan dengan:\n<code>/autodelete off</code>',
        )
        return

    sub = args[0].lower()

    if sub == 'off':
        await client.mdb.outvars('BOT_VARS', 'AUTO_DELETE_DELAY')
        await client.mdb.invar('BOT_VARS', 'AUTO_DELETE_DELAY', 'off')
        await client.var.fetching()
        await _reload()
        await message.reply(
            '🔴 <b>Auto-delete berhasil dimatikan.</b>\n'
            'Konten tidak akan dihapus otomatis.',
        )
        return

    if sub == 'on':
        if len(args) < 2:
            await message.reply(
                '❌ Masukkan durasi dalam menit.\n'
                'Contoh: <code>/autodelete on 15</code>',
            )
            return
        try:
            menit = int(args[1])
            if menit <= 0:
                raise ValueError
        except ValueError:
            await message.reply(
                '❌ Durasi harus berupa angka positif (menit).\n'
                'Contoh: <code>/autodelete on 15</code>',
            )
            return

        detik = menit * 60
        await client.mdb.outvars('BOT_VARS', 'AUTO_DELETE_DELAY')
        await client.mdb.invar('BOT_VARS', 'AUTO_DELETE_DELAY', detik)
        await client.var.fetching()
        await _reload()
        await message.reply(
            f'🟢 <b>Auto-delete berhasil diaktifkan!</b>\n'
            f'⏱ Konten akan otomatis dihapus setelah <b>{menit} menit</b>.',
        )
        return

    await message.reply(
        '❌ Perintah tidak dikenal.\n\n'
        '<b>Penggunaan:</b>\n'
        '<code>/autodelete</code> — cek status\n'
        '<code>/autodelete on &lt;menit&gt;</code> — aktifkan\n'
        '<code>/autodelete off</code> — matikan',
    )


Bot.add_handler(
    MessageHandler(
        setcaption,
        filters=command(Bot.cmd.setcaption) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        delcaption,
        filters=command(Bot.cmd.delcaption) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        getcaption,
        filters=command(Bot.cmd.getcaption) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        setpromo,
        filters=command(Bot.cmd.setpromo) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        delpromo,
        filters=command(Bot.cmd.delpromo) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        getpromo,
        filters=command(Bot.cmd.getpromo) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        autodelete_cmd,
        filters=command(Bot.cmd.autodelete) & private,
    ),
)


# ---------------------------------------------------------------------------
# /setquotatext  /getquota
# ---------------------------------------------------------------------------
# CATATAN: jumlah kuota /view harian sekarang diatur lewat /setview limit
# (plugins/view.py) — SAMA persis dengan VIEW_LIMIT di bot asli Kingsuga.
# Dua perintah di bawah ini cuma untuk kustomisasi TEKS notice-nya, bukan
# angka limitnya (sudah tidak ada /setquota terpisah lagi supaya tidak
# ada dua sumber kebenaran yang bisa bentrok).

@decorator.Admins
async def setquotatext(client: Bot, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(
            '<blockquote><b>📝 Kirimkan teks notice yang tampil saat '
            'kuota /view harian member habis (yang sudah join FSub).\n\n'
            'Contoh:\n<code>/setquotatext Kuota harian kamu sudah habis, '
            'yuk upgrade VIP!</code>\n\n'
            'Tombol 🌟 PROMO VIP (/setpromo) otomatis ditempel di bawah '
            'teks ini.\n\nUntuk atur ANGKA kuotanya, pakai '
            '/setview limit &lt;n&gt;.</b></blockquote>',
        )
        return

    text = parts[1].strip()
    await client.mdb.outvars('BOT_VARS', 'QUOTA_TEXT')
    await client.mdb.invar('BOT_VARS', 'QUOTA_TEXT', text)
    await client.var.fetching()
    await _reload()

    await message.reply(
        f'<blockquote><b>✅ Notice kuota habis berhasil diatur ke:\n\n'
        f'<code>{text}</code></b></blockquote>',
    )


@decorator.Admins
async def getquota(client: Bot, message: Message):
    status = (
        f'{helpers.view_limit}x /view per hari' if helpers.view_limit > 0
        else 'Unlimited (tanpa batas)'
    )
    await message.reply(
        f'<blockquote><b>⚙️ Kuota /view Harian\n\n'
        f'Status : {status}\n'
        f'(atur lewat /setview limit &lt;n&gt;)\n\n'
        f'Notice : <code>{helpers.quota_text or "(default bawaan)"}</code>\n'
        f'Promo VIP : {"✅ aktif" if helpers.promolink else "❌ belum diset (/setpromo)"}'
        f'</b></blockquote>',
    )


Bot.add_handler(
    MessageHandler(
        setquotatext,
        filters=command(Bot.cmd.setquotatext) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        getquota,
        filters=command(Bot.cmd.getquota) & private,
    ),
)
