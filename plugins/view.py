"""
plugins/view.py
================
Fitur /view — porting dari fsub2 (Kingsuga), disesuaikan ke arsitektur
single-bot masterfs (satu channel database via `Bot.env.DATABASE_ID`,
bukan `CH_BASE` per-clone seperti di fsub2).

PENTING soal /setview limit:
  Sama seperti bot ASLI Kingsuga, angka di `/setview limit <n>` adalah
  KUOTA /view HARIAN per-member (default 3x/hari) — bukan jumlah sampel
  yang di-scan. Tiap klik tombol angka = 1 kuota terpakai, reset otomatis
  tiap ganti hari. Ukuran sampel scan-nya sendiri konstan (VIEW_SCAN_SIZE
  di bawah), tidak bisa diubah lewat command.
  Kalau kuota member habis:
    - Member yang BELUM join FSub -> tetap disuruh join dulu.
    - Member yang SUDAH join FSub -> langsung diarahkan order VIP
      (notice + tombol 🌟 PROMO VIP dari /setpromo) untuk kuota tanpa
      batas. Admin selalu bebas dari limit ini.

Ada 2 cara memicu fitur ini:
  1. Command  /view          — bisa dipanggil kapan saja di private chat.
  2. Tombol   "📁 Buka Media" — ditempel di pesan /start (welcome),
     TAPI hanya muncul untuk member yang sudah join semua FSub (lihat
     plugins/start.py + Helpers.openviewkb() di plugins/helpers.py).
     Handler tombol ini (`cb_openview`) tetap melakukan cek join ulang
     sebagai jaga-jaga kalau user sempat leave channel setelah tombol
     tampil.

Kedua jalur berujung ke fungsi yang sama (`_send_view_list`), yang men-
scan channel database, memilih sejumlah media acak (VIEW_SCAN_SIZE),
lalu menampilkan tombol angka untuk dipilih. Saat sebuah tombol angka
diklik, media dikirim ke user lewat `Helpers.copymsgs()` yang sudah
otomatis:
  - menghormati /setcaption   (caption otomatis)
  - menghormati Protect Content (/set -> Protect Content)
  - menempel tombol 🌟 PROMO VIP (/setpromo) kalau di-set

...dan hasil kirimannya tetap dijadwalkan Helpers.schedule_autodelete()
seperti konten yang dibagikan lewat /start <payload> — jadi tunduk pada
pengaturan /autodelete yang sama.

CATATAN PENTING soal pesan force-join:
  Pesan "wajib join" yang tampil saat user membuka tautan /start
  <payload> (mis. link hasil /batch) TIDAK diubah oleh plugin ini —
  pesan itu tetap sepenuhnya mengikuti konten FORCE_MESSAGE (/set ->
  Force Text) apa adanya, karena memang terikat pada konten yang
  dibagikan lewat tautan tsb. Fitur /view di sini memakai teks
  peringatan join-nya SENDIRI (JOIN_REQUIRED_TEXT di bawah), terpisah
  dari FORCE_MESSAGE, supaya tidak mencampur dua konteks yang berbeda.

/setview (admin only)
----------------------
  /setview            - cek status ON/OFF + kuota harian saat ini
  /setview on         - aktifkan fitur
  /setview off        - nonaktifkan fitur
  /setview limit <n>  - atur kuota /view harian per-member (0 = unlimited)
"""

import asyncio
import contextlib
import random

from pyrogram.errors import FloodWait, RPCError
from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.filters import regex
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.handlers import MessageHandler
from pyrogram.types import CallbackQuery
from pyrogram.types import Message

from .helpers import decorator
from .helpers import helpers
from bot.client import Bot
from bot.utils.coloredkb import btn
from bot.utils.coloredkb import ckb
from bot.utils.coloredkb import edit_colored
from bot.utils.coloredkb import send_colored

VIEW_PAGE_SIZE = 20  # tombol angka per halaman
VIEW_SCAN_SIZE = 50  # jumlah ID acak yang di-scan tiap /view (konstan,
                      # TIDAK terikat ke /setview limit — itu kuota harian)

JOIN_REQUIRED_TEXT = (
    '<b>⚠️ Untuk dapat menggunakan fitur ini, silahkan join channel/group '
    'berikut terlebih dahulu!\n\nSetelah join, ketik /view kembali atau '
    'klik tombol 📂 Buka Media di menu /start.</b>'
)

# Cache hasil scan valid_ids per user: {user_id: [msg_id, ...]}
# (in-memory saja, sama seperti fsub2 — cukup untuk navigasi next/prev
# selama proses bot berjalan, tidak perlu persist ke DB)
_view_cache: dict[int, list[int]] = {}


def _set_view_cache(user_id: int, msg_ids: list[int]) -> None:
    _view_cache[user_id] = msg_ids


def _get_view_cache(user_id: int) -> list[int]:
    return _view_cache.get(user_id, [])


def _build_view_buttons(msg_ids: list[int], page: int = 0) -> list[list[dict]]:
    """
    Buat baris tombol angka dari daftar msg_id dengan pagination.
    Format callback: view_get:{msg_id}
    Format nav     : view_page:{page}
    5 tombol per baris, VIEW_PAGE_SIZE tombol per halaman.
    """
    total = len(msg_ids)
    total_pages = max(1, (total + VIEW_PAGE_SIZE - 1) // VIEW_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * VIEW_PAGE_SIZE
    page_ids = msg_ids[start_idx: start_idx + VIEW_PAGE_SIZE]

    buttons: list[list[dict]] = []
    row: list[dict] = []
    for i, mid in enumerate(page_ids, start=start_idx + 1):
        row.append(btn(str(i), data=f'view_get:{mid}', style='primary'))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav = []
    if page > 0:
        nav.append(btn('⬅️ Prev', data=f'view_page:{page - 1}', style='success'))
    nav.append(btn(f'📄 {page + 1}/{total_pages}', data='view_noop', style='primary'))
    if page < total_pages - 1:
        nav.append(btn('Next ➡️', data=f'view_page:{page + 1}', style='success'))
    if nav:
        buttons.append(nav)

    return buttons


def _listing_text(total: int, page: int, total_pages: int, sisa: int | None) -> str:
    autodel_note = ''
    if helpers.get_autodelete_delay() is not None:
        menit = helpers.get_autodelete_delay() // 60
        autodel_note = f'\n\n⏳ Media otomatis terhapus setelah {menit} menit.'
    quota_note = ''
    if sisa is not None:
        quota_note = (
            f'\n\n📊 Sisa kuota /view hari ini: <code>{sisa}x</code> dari '
            f'{helpers.view_limit}x\n⚠️ Setiap klik mengurangi 1 kuota harian kamu.'
        )
    return (
        '<blockquote><b>📂 Silahkan klik tombol angka di bawah ini untuk '
        'membuka media!\n\n'
        f'📋 Total konten: <code>{total}</code> | '
        f'Halaman: <code>{page + 1}/{total_pages}</code>'
        f'{quota_note}'
        f'{autodel_note}</b></blockquote>'
    )


async def _send_view_list(client: Bot, chat_id: int, user_id: int) -> None:
    """Scan channel database (Bot.env.DATABASE_ID), ambil sejumlah media
    acak, lalu kirim daftar tombol angka. Dipakai bareng oleh /view dan
    tombol 'Buka Media'."""
    wait_msg = await client.send_message(
        chat_id, '__Memuat daftar media, tunggu sebentar...__',
    )

    try:
        # FIX #2: get_chat_history() (messages.GetHistory) DILARANG dipakai
        # bot lewat MTProto untuk channel (BOT_METHOD_INVALID) — beda dari
        # get_messages() (channels.GetMessages) yang DIIZINKAN untuk bot.
        # Trik standar bot file-store: kirim 1 pesan dummy ke channel
        # database, ID pesan itu = (ID terakhir + 1), lalu langsung hapus.
        # Butuh bot jadi admin/punya hak kirim di channel database — yang
        # memang sudah wajib untuk fitur upload/copy lain di bot ini.
        dummy = await client.send_message(client.env.DATABASE_ID, '.')
        max_id = dummy.id - 1
        with contextlib.suppress(Exception):
            await dummy.delete()
    except Exception as er:
        await wait_msg.delete()
        await client.send_message(
            chat_id,
            f'<blockquote><b>❌ Gagal mengakses database media: '
            f'<code>{er}</code></b></blockquote>',
        )
        return

    if max_id < 1:
        await wait_msg.delete()
        await client.send_message(
            chat_id,
            '<blockquote><b>📭 Database media kosong atau tidak dapat '
            'diakses.</b></blockquote>',
        )
        return

    sample_size = min(VIEW_SCAN_SIZE, max_id)
    ids = random.sample(range(1, max_id + 1), sample_size)

    try:
        raw_msgs = await client.get_messages(client.env.DATABASE_ID, ids)
        valid_ids = [
            m.id for m in raw_msgs
            if m and not m.empty and (m.video or m.document or m.photo or m.audio)
        ]
    except Exception as er:
        await wait_msg.delete()
        await client.send_message(
            chat_id,
            f'<blockquote><b>❌ Gagal memuat konten: '
            f'<code>{er}</code></b></blockquote>',
        )
        return

    if not valid_ids:
        await wait_msg.delete()
        await client.send_message(
            chat_id,
            '<blockquote><b>📭 Tidak ada media ditemukan. Coba /view lagi '
            'untuk memuat konten lain.</b></blockquote>',
        )
        return

    _set_view_cache(user_id, valid_ids)
    total_pages = max(1, (len(valid_ids) + VIEW_PAGE_SIZE - 1) // VIEW_PAGE_SIZE)
    buttons = _build_view_buttons(valid_ids, page=0)

    sisa = None
    if user_id not in helpers.adminids and helpers.view_limit > 0:
        used = await helpers.quota_used_today(user_id)
        sisa = max(0, helpers.view_limit - used)

    await wait_msg.delete()
    await send_colored(
        client, chat_id,
        _listing_text(len(valid_ids), 0, total_pages, sisa),
        reply_markup=ckb(buttons),
    )


# ---------------------------------------------------------------------------
# /view
# ---------------------------------------------------------------------------

async def cmd_view(client: Bot, message: Message):
    if not message.from_user:
        return
    user = message.from_user.id

    if not helpers.view_enabled:
        await message.reply(
            '<blockquote><b>⛔ Fitur /view saat ini sedang dinonaktifkan '
            'oleh admin.</b></blockquote>',
        )
        return

    nojoin_list = await helpers.nojoin(user)
    if nojoin_list:
        await send_colored(
            client, message.chat.id,
            JOIN_REQUIRED_TEXT,
            reply_markup=helpers.joinkb(nojoin_list),
        )
        return

    # Sudah join semua FSub, tapi kuota /view harian (/setview limit) sudah habis ->
    # jangan tampilkan daftar angka sama sekali, arahkan ke VIP langsung.
    if not await helpers.quota_remaining(user):
        await send_colored(
            client, message.chat.id,
            helpers.quota_notice_text(),
            reply_markup=helpers.quota_notice_markup(),
        )
        return

    await _send_view_list(client, message.chat.id, user)


# ---------------------------------------------------------------------------
# Tombol "📂 Buka Media" (dari pesan /start)
# ---------------------------------------------------------------------------

async def cb_openview(client: Bot, cq: CallbackQuery):
    user = cq.from_user.id

    if not helpers.view_enabled:
        await cq.answer('⛔ Fitur ini sedang dinonaktifkan.', show_alert=True)
        return

    # Wajib untuk member yang SUDAH join saja — tombol ini memang cuma
    # dipasang di pesan welcome saat user lolos cek FSub (plugins/
    # start.py), tapi tetap dicek ulang di sini kalau-kalau user sempat
    # leave channel setelah tombolnya tampil.
    nojoin_list = await helpers.nojoin(user)
    if nojoin_list:
        await cq.answer('⚠️ Kamu harus join channel/group dulu!', show_alert=True)
        await send_colored(
            client, cq.message.chat.id,
            JOIN_REQUIRED_TEXT,
            reply_markup=helpers.joinkb(nojoin_list),
        )
        return

    # Sudah join semua FSub, tapi kuota /view harian (/setview limit) sudah habis ->
    # jangan tampilkan daftar angka sama sekali, arahkan ke VIP langsung.
    if not await helpers.quota_remaining(user):
        await cq.answer('⛔ Kuota harian kamu sudah habis.', show_alert=True)
        await send_colored(
            client, cq.message.chat.id,
            helpers.quota_notice_text(),
            reply_markup=helpers.quota_notice_markup(),
        )
        return

    await cq.answer()
    await _send_view_list(client, cq.message.chat.id, user)


# ---------------------------------------------------------------------------
# Navigasi halaman
# ---------------------------------------------------------------------------

async def cb_view_noop(client: Bot, cq: CallbackQuery):
    await cq.answer()


async def cb_view_page(client: Bot, cq: CallbackQuery):
    user = cq.from_user.id

    try:
        _, page_str = cq.data.split(':')
        page = int(page_str)
    except Exception:
        await cq.answer('❌ Data tidak valid.', show_alert=True)
        return

    cached = _get_view_cache(user)
    if not cached:
        await cq.answer('⚠️ Sesi habis, ketik /view lagi.', show_alert=True)
        return

    total_pages = max(1, (len(cached) + VIEW_PAGE_SIZE - 1) // VIEW_PAGE_SIZE)
    buttons = _build_view_buttons(cached, page=page)

    sisa = None
    if user not in helpers.adminids and helpers.view_limit > 0:
        used = await helpers.quota_used_today(user)
        sisa = max(0, helpers.view_limit - used)

    try:
        await edit_colored(
            client, cq.message.chat.id, cq.message.id,
            text=_listing_text(len(cached), page, total_pages, sisa),
            reply_markup=ckb(buttons),
        )
    except Exception:
        pass
    await cq.answer()


# ---------------------------------------------------------------------------
# Ambil & kirim media terpilih
# ---------------------------------------------------------------------------

async def cb_view_get(client: Bot, cq: CallbackQuery):
    user = cq.from_user.id

    try:
        _, msg_id_str = cq.data.split(':')
        msg_id = int(msg_id_str)
    except Exception:
        await cq.answer('❌ Data tidak valid.', show_alert=True)
        return

    if not helpers.view_enabled:
        await cq.answer('⛔ Fitur ini sedang dinonaktifkan.', show_alert=True)
        return

    # Jaga-jaga: user sempat leave channel FSub setelah daftar tombol tampil
    nojoin_list = await helpers.nojoin(user)
    if nojoin_list:
        await cq.answer('⚠️ Kamu harus join channel/group dulu!', show_alert=True)
        await send_colored(
            client, cq.message.chat.id,
            JOIN_REQUIRED_TEXT,
            reply_markup=helpers.joinkb(nojoin_list),
        )
        return

    # Kuota /view harian (/setview limit) — kalau sudah habis, tolak & arahkan ke
    # tombol PROMO VIP alih-alih kirim medianya.
    if not await helpers.quota_ok(user):
        await cq.answer('⛔ Kuota harian kamu sudah habis.', show_alert=True)
        await send_colored(
            client, cq.message.chat.id,
            helpers.quota_notice_text(),
            reply_markup=helpers.quota_notice_markup(),
        )
        return

    # Jawab callback SEKARANG sebelum proses network lain (hindari
    # QUERY_ID_INVALID kalau get_messages/copy lambat).
    try:
        await cq.answer('⏳ Sedang memuat media...')
    except Exception:
        pass

    try:
        msg = await client.get_messages(client.env.DATABASE_ID, msg_id)
    except Exception as er:
        await cq.message.reply(
            f'<blockquote><b>❌ Gagal mengambil media: '
            f'<code>{er}</code></b></blockquote>',
        )
        return

    if not msg or msg.empty:
        await cq.message.reply(
            '<blockquote><b>❌ Media tidak ditemukan di database.</b></blockquote>',
        )
        return

    sent_ids: list[int] = []
    try:
        sid = await helpers.copymsgs(msg, user)
        if sid:
            sent_ids.append(sid)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            sid = await helpers.copymsgs(msg, user)
            if sid:
                sent_ids.append(sid)
        except RPCError as er:
            await cq.message.reply(
                f'<blockquote><b>❌ Gagal mengirim media: '
                f'<code>{er}</code></b></blockquote>',
            )
            return
    except RPCError as er:
        await cq.message.reply(
            f'<blockquote><b>❌ Gagal mengirim media: '
            f'<code>{er}</code></b></blockquote>',
        )
        return

    if not sent_ids:
        await cq.message.reply(
            '<blockquote><b>❌ Gagal mengirim media.</b></blockquote>',
        )
        return

    # Info sisa kuota setelah berhasil kirim (mirip UX Kingsuga) — cuma
    # relevan kalau limitnya aktif & bukan admin.
    if user not in helpers.adminids and helpers.view_limit > 0:
        used = await helpers.quota_used_today(user)
        sisa = max(0, helpers.view_limit - used)
        if sisa > 0:
            info = await cq.message.reply(
                f'<blockquote>✅ Media berhasil dikirim!\n'
                f'📊 Sisa kuota hari ini: <code>{sisa}x</code></blockquote>',
            )
        else:
            info = await cq.message.reply(
                '<blockquote>✅ Media berhasil dikirim!\n⛔ Kuota /view kamu '
                'hari ini sudah habis. Coba lagi besok, atau order VIP untuk '
                'akses tanpa batas!</blockquote>',
            )
        sent_ids.append(info.id)

    # Auto-delete — tunduk pada pengaturan /autodelete yang sama dengan
    # konten yang dibagikan lewat /start <payload>.
    asyncio.create_task(helpers.schedule_autodelete(user, sent_ids))


# ---------------------------------------------------------------------------
# /setview (admin only)
# ---------------------------------------------------------------------------

@decorator.Admins
async def setview_cmd(client: Bot, message: Message):
    args = message.command[1:]

    if not args:
        status = '✅ ON' if helpers.view_enabled else '❌ OFF'
        limit_desc = (
            f'{helpers.view_limit}x per hari' if helpers.view_limit > 0
            else 'Unlimited (0 = tanpa batas)'
        )
        await message.reply(
            f'<blockquote><b>⚙️ Pengaturan Fitur /view\n\n'
            f'Status       : {status}\n'
            f'Kuota harian : {limit_desc}\n\n'
            f'Cara penggunaan:\n'
            f'• /setview on — Aktifkan fitur /view\n'
            f'• /setview off — Nonaktifkan fitur /view\n'
            f'• /setview limit 3 — Atur kuota /view harian per-member\n'
            f'• /setview limit 0 — Kuota tanpa batas (unlimited)\n\n'
            f'Kalau kuota member habis: belum join FSub -> disuruh join '
            f'dulu, sudah join -> langsung diarahkan order VIP '
            f'(/setpromo).</b></blockquote>',
        )
        return

    sub = args[0].lower()

    if sub == 'on':
        await client.mdb.outvars('BOT_VARS', 'VIEW_ENABLED')
        await client.mdb.invar('BOT_VARS', 'VIEW_ENABLED', True)
        await client.var.fetching()
        await helpers.cached()  # FIX: reload() sync tidak isi ulang cacheids (invite link FSub), pakai cached() supaya tombol Join tidak hilang
        await message.reply(
            '<blockquote><b>✅ Fitur /view berhasil <u>diaktifkan</u>!</b></blockquote>',
        )
        return

    if sub == 'off':
        await client.mdb.outvars('BOT_VARS', 'VIEW_ENABLED')
        await client.mdb.invar('BOT_VARS', 'VIEW_ENABLED', False)
        await client.var.fetching()
        await helpers.cached()  # FIX: reload() sync tidak isi ulang cacheids (invite link FSub), pakai cached() supaya tombol Join tidak hilang
        await message.reply(
            '<blockquote><b>❌ Fitur /view berhasil <u>dinonaktifkan</u>!</b></blockquote>',
        )
        return

    if sub == 'limit':
        if len(args) < 2:
            await message.reply(
                '<blockquote><b>⚠️ Berikan jumlah kuota harian.\n'
                'Contoh: /setview limit 3 (atau 0 untuk unlimited)</b></blockquote>',
            )
            return
        try:
            new_limit = int(args[1])
            if new_limit < 0:
                raise ValueError
        except ValueError:
            await message.reply(
                '<blockquote><b>❌ Jumlah harus berupa angka 0 atau lebih '
                '(0 = unlimited).</b></blockquote>',
            )
            return
        await client.mdb.outvars('BOT_VARS', 'VIEW_LIMIT')
        await client.mdb.invar('BOT_VARS', 'VIEW_LIMIT', new_limit)
        await client.var.fetching()
        await helpers.cached()  # FIX: reload() sync tidak isi ulang cacheids (invite link FSub), pakai cached() supaya tombol Join tidak hilang
        desc = f'{new_limit}x per hari' if new_limit > 0 else 'unlimited (tanpa batas)'
        await message.reply(
            f'<blockquote><b>✅ Kuota /view harian berhasil diubah menjadi '
            f'<code>{desc}</code>!</b></blockquote>',
        )
        return

    await message.reply(
        '<blockquote><b>⚠️ Argumen tidak dikenal.\n\n'
        'Penggunaan:\n'
        '• /setview on\n'
        '• /setview off\n'
        '• /setview limit [angka]</b></blockquote>',
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

Bot.add_handler(
    MessageHandler(
        cmd_view,
        filters=command(Bot.cmd.view) & private,
    ),
)
Bot.add_handler(
    MessageHandler(
        setview_cmd,
        filters=command(Bot.cmd.setview) & private,
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cb_openview,
        filters=regex(r'^openview$'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cb_view_noop,
        filters=regex(r'^view_noop$'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cb_view_page,
        filters=regex(r'^view_page:'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cb_view_get,
        filters=regex(r'^view_get:'),
    ),
)
