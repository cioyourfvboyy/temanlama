"""
plugins/fsubguard.py
=====================
Indikator REAL-TIME untuk channel/grup FSub yang bermasalah.

Selama ini status FSub cuma kelihatan kalau admin cek manual lewat /health,
atau setelah helpers.cached() jalan lagi (start bot / ganti setting). Kalau
di tengah jalan bot tiba-tiba di-demote dari admin, di-kick, atau di-ban dari
salah satu channel/grup FSub, TIDAK ADA yang tahu sampai user mulai komplain
force-sub tidak jalan.

Plugin ini dengerin event `ChatMemberUpdated` — update resmi yang otomatis
dikirim Telegram tiap kali status bot berubah di suatu chat (naik/turun
admin, di-restrict, di-kick, di-ban, dsb). Begitu perubahan itu kena salah
satu ID di FSUB_IDS, admin langsung dikirim notifikasi lewat pesan bot —
tanpa perlu nunggu /health dijalankan manual.

Catatan: hanya menangkap perubahan yang terjadi SELAGI bot online. Untuk
FSub yang sudah bermasalah SEBELUM bot terakhir start (mis. bot sempat
di-kick saat mati), tetap kelihatan lewat /health seperti biasa — dua-duanya
saling melengkapi.
"""
from __future__ import annotations

from pyrogram.enums import ChatMemberStatus
from pyrogram.handlers import ChatMemberUpdatedHandler
from pyrogram.types import ChatMemberUpdated

from .helpers import helpers
from bot.client import Bot
from bot.utils.coloredkb import send_colored

# Status baru yang dianggap "FSub ini rusak" -> (emoji, alasan singkat)
_BAD_STATUS_REASON = {
    ChatMemberStatus.BANNED: ('❌', 'Bot DIBANNED dari'),
    ChatMemberStatus.LEFT: ('🚪', 'Bot keluar / dikeluarkan dari'),
    ChatMemberStatus.RESTRICTED: ('⚠️', 'Bot dibatasi (restricted) di'),
}


async def _on_membership_change(client: Bot, update: ChatMemberUpdated):
    try:
        cid = update.chat.id
        if cid not in helpers.fsubcids:
            return  # bukan channel/grup FSub, abaikan

        me = getattr(client, 'me', None)
        target = (
            update.new_chat_member.user if update.new_chat_member
            else (update.old_chat_member.user if update.old_chat_member else None)
        )
        if not me or not target or target.id != me.id:
            return  # perubahan status member lain, bukan bot ini sendiri

        new_status = update.new_chat_member.status if update.new_chat_member else ChatMemberStatus.LEFT
        old_status = update.old_chat_member.status if update.old_chat_member else None

        reason = _BAD_STATUS_REASON.get(new_status)
        if not reason and old_status == ChatMemberStatus.ADMINISTRATOR and new_status == ChatMemberStatus.MEMBER:
            reason = ('⚠️', 'Bot diturunkan dari admin (bukan admin lagi) di')

        if not reason:
            return  # perubahan normal (mis. balik jadi admin) -> tidak perlu alert

        emoji, alasan = reason
        idx = helpers.fsubcids.index(cid) + 1
        chat_title = update.chat.title or (
            f'@{update.chat.username}' if update.chat.username else str(cid)
        )

        # Tandai cache invalid supaya /health & tombol Join langsung update,
        # tidak perlu nunggu siklus helpers.cached() berikutnya.
        if cid in helpers.cacheids:
            helpers.cacheids[cid]['ilink'] = None

        text = (
            f'<blockquote><b>{emoji} FSub #{idx} bermasalah!</b>\n\n'
            f'{alasan} <b>{chat_title}</b> (<code>{cid}</code>).\n\n'
            'Selama belum diperbaiki, Force Subscribe untuk channel/grup ini '
            'TIDAK AKTIF — user bisa lolos tanpa join, atau tombol Join bisa '
            'hilang/error.\n\n'
            'Perbaiki dengan menambahkan lagi bot sebagai admin di sana, atau '
            'hapus dari daftar FSub lewat /set kalau memang sudah tidak '
            'dipakai.</blockquote>'
        )
        for admin_id in helpers.adminids:
            try:
                await send_colored(client, admin_id, text)
            except Exception:
                pass  # admin belum pernah /start bot, atau memblokir bot

        client.log.warning(f'[FSubGuard] FSub #{idx} ({cid}): {alasan} {chat_title}')

    except Exception as e:
        client.log.warning(f'[FSubGuard] Error: {e}')


Bot.add_handler(ChatMemberUpdatedHandler(_on_membership_change))
