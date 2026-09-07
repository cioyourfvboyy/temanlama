"""
bot/utils/coloredkb.py
=======================
Helper untuk membuat dan mengirim inline keyboard BERWARNA.

Latar belakang teknis singkat (lihat juga bot/utils/botapi.py):
- Pyrofork (MTProto) belum mendukung field `style` pada InlineKeyboardButton.
- Bot API HTTP (sejak versi 9.4, Feb 2026) sudah mendukungnya.
- Karena itu modul ini membangun keyboard sebagai dict JSON mentah (bukan
  objek pyrogram.types.InlineKeyboardButton) dan mengirimkannya lewat
  bot/utils/botapi.py — BUKAN lewat client.send_message() bawaan Pyrofork.

CARA PAKAI
----------
Pengganti pola lama:
    from pyrogram.helpers import ikb
    markup = ikb([[('Close', 'home-close')]])
    await message.reply('teks', reply_markup=markup)

Jadi:
    from bot.utils.coloredkb import ckb, btn, send_colored, edit_colored
    markup = ckb([[btn('Close', 'home-close', style='danger')]])
    await send_colored(client, chat_id, 'teks', reply_markup=markup)

`btn(...)` membuat satu tombol (dict). `ckb(...)` membungkus list-of-rows
jadi struktur `inline_keyboard` yang valid untuk Bot API.

Tombol yang TIDAK diberi `style` akan tampil dengan warna default Telegram
(biru/primary) — sama seperti sebelumnya, jadi aman dicampur dengan kode
lama yang belum diupdate.

WARNA YANG TERSEDIA (Bot API 9.4+) — dikonfirmasi dari dokumentasi resmi
-------------------------------------------------------------------------
- None / 'primary'   -> warna default (biru/accent)
- 'success'           -> hijau (konfirmasi, aksi positif)
- 'danger'            -> merah (aksi destruktif: hapus, stop, batal)

Tidak ada opsi abu-abu/netral di Bot API — hanya 3 nilai di atas yang sah.
Jika kamu kirim nilai lain, Telegram akan menolak request (error 400).

Callback query dari tombol-tombol ini TETAP ditangani seperti biasa oleh
handler Pyrofork (CallbackQueryHandler) — tidak ada perubahan di sisi itu,
karena update callback_query datang dari Telegram apa adanya, terlepas
dari API mana yang dipakai untuk mengirim pesannya.
"""

from __future__ import annotations

from typing import Any

from .botapi import BotAPI

VALID_STYLES = {'primary', 'success', 'danger'}


# ---------------------------------------------------------------------------
# Premium animated custom emoji.
# ---------------------------------------------------------------------------
# Dipakai di DUA tempat dengan ID yang SAMA:
#   1. Teks pesan       -> lewat premium_emoji() / tag <tg-emoji emoji-id="...">
#   2. Ikon pada tombol  -> lewat pbtn() / field resmi Bot API 9.4+
#      `icon_custom_emoji_id` (ikon tampil DI tombol, terpisah dari label
#      teksnya — bukan di dalam label, karena label tombol cuma boleh
#      plain text).
#
# Isi value di bawah dengan custom_emoji_id asli kamu (angka panjang),
# didapat dari forward stiker/emoji premium ke @RawDataBot atau sejenisnya.
# Selama masih None, kode otomatis fallback ke emoji unicode biasa supaya
# TIDAK ERROR (ID placeholder/asal akan ditolak Telegram dengan
# CUSTOM_EMOJI_INVALID, baik di teks maupun di tombol).
PREMIUM_EMOJI_IDS: dict[str, str | None] = {
    'join': '5458603043203327669',     # 🔔 emoji di pesan & tombol Join Channel
    'tryagain': '5258420634785947640', # 🔄 emoji di pesan & tombol Coba Lagi
    'config': '5341715473882955310',   # ⚙️ emoji di pesan & tombol-tombol menu Configuration
    'info': '5341715473882955310',     # ⚙️ reuse — emoji di header pesan /info
    'dev': '5260208672620965597',      # 🔔 reuse — emoji di tombol Developer
    'store': '5226702984204797593',    # 🔄 reuse — emoji di tombol Bot Store
    'owner': '5258012913540562827',    # 🔔 reuse — emoji di tombol Owner
    'view': '5258514780469075716',      # 📁 emoji di tombol "Buka Media" — ISI ID-nya di sini
}


def pbtn(
    key: str,
    text: str,
    data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    fallback: str = '',
) -> dict:
    """
    Sama seperti btn(), tapi otomatis pasang ikon premium di tombol lewat
    field `icon_custom_emoji_id` (Bot API 9.4+) kalau ID untuk `key` di
    PREMIUM_EMOJI_IDS sudah diisi.

    - Kalau ID ADA  -> tombol dapat ikon animasi premium, label tetap
                       teks bersih tanpa emoji unicode di depannya.
    - Kalau ID BELUM ADA (masih None) -> fallback aman: emoji unicode
                       biasa (`fallback`) ditempel di depan label teks,
                       SAMA SEPERTI cara lama, tidak ada risiko error.
    """
    icon_id = PREMIUM_EMOJI_IDS.get(key)
    label = text if icon_id else (f'{fallback} {text}'.strip() if fallback else text)
    button = btn(label, data=data, url=url, style=style)
    if icon_id:
        button['icon_custom_emoji_id'] = icon_id
    return button


def premium_emoji(key: str, fallback: str) -> str:
    """
    Kembalikan tag HTML <tg-emoji emoji-id="..."> kalau ID untuk `key`
    sudah diisi di PREMIUM_EMOJI_IDS, kalau belum kembalikan emoji
    unicode `fallback` biasa (aman, tidak akan bikin pesan gagal terkirim).
    """
    eid = PREMIUM_EMOJI_IDS.get(key)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


def btn(
    text: str,
    data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    copy_text: str | None = None,
) -> dict[str, Any]:
    """
    Buat satu tombol inline keyboard (dict, bukan objek Pyrogram).

    - text   : label tombol
    - data   : callback_data (mode default, sama seperti ikb biasa)
    - url    : kalau diisi, jadi tombol URL (callback_data diabaikan)
    - style  : 'primary' (default) | 'success' | 'danger'
    - copy_text : kalau diisi, jadi tombol copy-to-clipboard
    """
    if style is not None and style not in VALID_STYLES:
        raise ValueError(
            f"style harus salah satu dari {VALID_STYLES}, dapat: {style!r}",
        )

    button: dict[str, Any] = {'text': text}
    if url is not None:
        button['url'] = url
    elif copy_text is not None:
        # FIX: Bot API mengharuskan field `copy_text` berupa OBJECT
        # (CopyTextButton: {"text": "..."}), bukan string mentah.
        # Sebelumnya dikirim string langsung -> ditolak Telegram dengan
        # error 400 "Field copy_text must be of type Object".
        button['copy_text'] = {'text': copy_text}
    elif data is not None:
        button['callback_data'] = data

    if style is not None:
        button['style'] = style

    return button


def ckb(rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """
    Bungkus rows of buttons (hasil dari btn(...)) menjadi struktur
    `reply_markup` yang valid untuk Bot API: {"inline_keyboard": [...]}.
    """
    return {'inline_keyboard': rows}


def legacy_row(
    items: list[tuple],
    style: str | None = None,
) -> list[dict[str, Any]]:
    """
    Konversi cepat dari format lama yang dipakai project ini, yaitu
    tuple (text, data) atau (text, url, 'url'), menjadi satu row tombol
    ber-style. Berguna untuk migrasi cepat Markup.* di helpers.py tanpa
    menulis ulang semuanya dari nol.

        legacy_row([('Close', 'home-close')], style='danger')
        legacy_row([('Join', 'https://t.me/x', 'url')])
    """
    row = []
    for item in items:
        if len(item) == 3 and item[2] == 'url':
            row.append(btn(item[0], url=item[1], style=style))
        else:
            row.append(btn(item[0], data=item[1], style=style))
    return row


# ---------------------------------------------------------------------------
# Wrappers kirim/edit pesan via Bot API HTTP (bukan via Pyrofork)
# ---------------------------------------------------------------------------

async def send_colored(
    client,
    chat_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = 'HTML',
    disable_notification: bool = False,
    reply_to_message_id: int | None = None,
) -> dict[str, Any]:
    """
    Kirim pesan baru dengan keyboard berwarna lewat Bot API HTTP.
    Mengembalikan dict Message mentah dari Telegram (punya 'message_id', dst).

    `client` harus punya `client.env.BOT_TOKEN` (Bot kita sudah begitu).
    """
    async with BotAPI(client.env.BOT_TOKEN) as api:
        return await api.call('sendMessage', {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode,
            'reply_markup': reply_markup,
            'disable_notification': disable_notification,
            'reply_to_message_id': reply_to_message_id,
        })


async def edit_colored(
    client,
    chat_id: int,
    message_id: int,
    text: str | None = None,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str | None = 'HTML',
) -> dict[str, Any]:
    """
    Edit pesan yang sudah ada (boleh dikirim lewat Pyrofork ataupun Bot
    API — message_id & chat_id konsisten di kedua jalur) supaya keyboard-nya
    jadi berwarna.

    Kalau `text` None, hanya reply_markup yang diubah
    (editMessageReplyMarkup); kalau diisi, teks ikut diubah (editMessageText).
    """
    async with BotAPI(client.env.BOT_TOKEN) as api:
        if text is None:
            return await api.call('editMessageReplyMarkup', {
                'chat_id': chat_id,
                'message_id': message_id,
                'reply_markup': reply_markup,
            })
        return await api.call('editMessageText', {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'parse_mode': parse_mode,
            'reply_markup': reply_markup,
        })


async def answer_callback_colored(
    client,
    callback_query_id: str,
    text: str | None = None,
    show_alert: bool = False,
) -> bool:
    """Jawab callback query lewat Bot API HTTP (opsional, jarang perlu —
    biasanya cbq.answer() bawaan Pyrofork sudah cukup dan TIDAK perlu warna)."""
    async with BotAPI(client.env.BOT_TOKEN) as api:
        return await api.call('answerCallbackQuery', {
            'callback_query_id': callback_query_id,
            'text': text,
            'show_alert': show_alert,
        })
