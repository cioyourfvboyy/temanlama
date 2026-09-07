"""
plugins/autopurge.py
=====================
Auto hapus service message (join/leave member, pin pesan, ganti judul/
foto grup, dsb) di channel & grup tempat bot ini bertugas.

Porting dari fsub2 (Kingsuga) — bedanya di sana handler ini dipasang ke
BANYAK client sekaligus (bot utama + seluruh userbot fsub cluster) lewat
patch async ke `fsub._bot` yang menunggu semua bot itu selesai start.
masterfs cuma punya SATU Bot client (lihat bot/client.py), jadi tidak
perlu logika cluster/patch tersebut — cukup daftarkan RawUpdateHandler
satu kali langsung di sini, otomatis ke-load oleh plugins/__init__.py.

Tidak berpengaruh ke pesan konten biasa (foto/video/dokumen dsb) yang
dikirim manual oleh admin/user — hanya menyasar MessageService bawaan
Telegram (join/left/pin/edit title/edit foto/create/migrate).
"""

from pyrogram import raw
from pyrogram.errors import ChatAdminRequired, MessageDeleteForbidden, RPCError
from pyrogram.handlers import RawUpdateHandler

from bot.client import Bot

RAW_SERVICE_TYPES = (
    raw.types.MessageActionPinMessage,
    raw.types.MessageActionChatEditPhoto,
    raw.types.MessageActionChatDeletePhoto,
    raw.types.MessageActionChatEditTitle,
    raw.types.MessageActionChatAddUser,
    raw.types.MessageActionChatDeleteUser,
    raw.types.MessageActionChatCreate,
    raw.types.MessageActionChannelCreate,
    raw.types.MessageActionChatMigrateTo,
)


async def _raw_purge(client, update, users, chats):
    """Raw handler — tangkap & hapus service message di channel/grup."""
    try:
        # Hanya proses UpdateNewChannelMessage atau UpdateNewMessage
        if not isinstance(update, (
            raw.types.UpdateNewChannelMessage,
            raw.types.UpdateNewMessage,
        )):
            return

        msg = update.message

        # Hanya proses MessageService
        if not isinstance(msg, raw.types.MessageService):
            return

        # Hanya action yang perlu dihapus
        if not isinstance(msg.action, RAW_SERVICE_TYPES):
            return

        # Resolve chat id
        peer = msg.peer_id
        if isinstance(peer, raw.types.PeerChannel):
            real_chat_id = int(f"-100{peer.channel_id}")
        elif isinstance(peer, raw.types.PeerChat):
            real_chat_id = -peer.chat_id
        else:
            return

        await client.delete_messages(real_chat_id, msg.id)
        Bot.log.info(
            f"[AutoPurge] ✅ Deleted action={type(msg.action).__name__} "
            f"chat={real_chat_id}",
        )

    except (ChatAdminRequired, MessageDeleteForbidden):
        # Bot bukan admin di chat tsb — diam saja
        pass
    except RPCError:
        pass
    except Exception as e:
        Bot.log.warning(f"[AutoPurge] Error: {e}")


# Satu-satunya Bot client di project ini → cukup satu handler.
Bot.add_handler(RawUpdateHandler(_raw_purge), group=999)

