import asyncio

from pyrogram.errors import FloodWait
from pyrogram.errors import RPCError
from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from .helpers import helpers
from bot.client import Bot
from bot.utils.coloredkb import send_colored
from bot.utils.coloredkb import premium_emoji


async def start(client: Bot, message: Message):
    if not message.from_user:
        return
    user = message.from_user.id
    if user < 0:  # skip channels/groups
        return

    await client.mdb.inusr(user)

    # FIX: jangan pakai message.from_user.mention(style='html') — di fork
    # Pyrogram ini hasilnya HTML tidak valid (atribut href tidak ter-quote
    # dengan benar), bikin Bot API gagal parse entities. Bangun manual saja.
    def html_escape(s: str) -> str:
        return (
            s.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
        )

    fname = html_escape(message.from_user.first_name or 'User')
    mention = f'<a href="tg://user?id={user}">{fname}</a>'

    def esc(s: str) -> str:
        return (
            s.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )

    def build_join_text() -> str:
        # Emoji premium di header pesan join (PREMIUM_EMOJI_IDS['join']
        # di coloredkb.py). Seluruh pesan (header + body) dibuat bold.
        header = f'{premium_emoji("join", "🔔")} Wajib Join Channel Berikut!'
        body = esc(helpers.forcemsg) if helpers.forcemsg else '⚠️ Wajib join dulu!'
        return f'<b>{header}\n\n{body}</b>'

    def build_force_with_tryagain_text() -> str:
        # Sama seperti di atas + baris kecil untuk tombol "Coba Lagi" (cuma
        # muncul saat user akses lewat /start <payload>). Seluruh pesan
        # (header + body + footer) dibuat bold.
        header = f'{premium_emoji("join", "🔔")} Wajib Join Channel Berikut!'
        body = esc(helpers.forcemsg) if helpers.forcemsg else '⚠️ Wajib join dulu!'
        footer = f'{premium_emoji("tryagain", "🔄")} Sudah join semua? Klik tombol Coba Lagi.'
        return f'<b>{header}\n\n{body}\n\n{footer}</b>'

    def build_start_text() -> str:
        raw = helpers.startmsg or '👋 Halo! Selamat datang.'
        body = esc(raw)
        return f'<b>Halo {mention}!\n\n{body}</b>'

    if len(message.command) == 1:
        # /start tanpa payload
        if user in helpers.adminids:
            await send_colored(
                client,
                message.chat.id,
                build_start_text() if helpers.startmsg else f'<b>👋 Halo Admin {mention}!</b>',
                reply_markup=helpers.admikb(),
            )
        else:
            # Cek wajib join dulu sebelum tampilkan startmsg
            nojoin_list = await helpers.nojoin(user)
            bttn = await helpers.usrikb(message, user, nojoin_list)
            # FIX: keputusan blokir HARUS berdasar nojoin_list saja, bukan
            # `nojoin_list and bttn`. Sebelumnya, kalau user belum join tapi
            # bttn gagal dibuat/kosong (mis. invite_link kosong), kondisi ini
            # jadi False -> user LOLOS masuk startmsg padahal belum join
            # channel manapun (bug bypass fsub).
            if nojoin_list:
                # User belum join → tampilkan forcemsg + tombol join
                # (kalau ada) + tombol "📂 Buka Media" tetap ikut
                # ditampilkan (lihat Helpers.openviewkb()). Kalau nanti
                # user klik tombol itu sebelum join, handler `^openview$`
                # di plugins/view.py akan menolak & memberi tahu "wajib
                # join dulu" beserta tombol join-nya lagi.
                await send_colored(
                    client,
                    message.chat.id,
                    build_join_text(),
                    reply_markup=helpers.openviewkb(bttn),
                )
            else:
                # User sudah join → tampilkan welcome + tombol "📂 Buka
                # Media" (fitur /view, lihat plugins/view.py).
                await send_colored(
                    client,
                    message.chat.id,
                    build_start_text(),
                    reply_markup=helpers.openviewkb(bttn),
                )
        return

    # /start <payload> — cek join sebelum kirim file
    nojoin_list = await helpers.nojoin(user)
    bttn = await helpers.usrikb(message, user, nojoin_list)
    if nojoin_list:
        await send_colored(
            client,
            message.chat.id,
            build_force_with_tryagain_text(),
            reply_markup=bttn,
        )
        return

    mids = helpers.decode(message.command[1])
    sent_ids = []
    for msg in await helpers.getmsgs(mids):
        try:
            sid = await helpers.copymsgs(msg, user)
            if sid:
                sent_ids.append(sid)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            client.log.warning(str(e))
        except RPCError:
            continue
    if sent_ids:
        # Jadwalkan auto-delete (no-op kalau /autodelete belum diaktifkan)
        asyncio.create_task(helpers.schedule_autodelete(user, sent_ids))
    return


Bot.add_handler(
    MessageHandler(
        start,
        filters=command(Bot.cmd.start) & private,
    ),
)
