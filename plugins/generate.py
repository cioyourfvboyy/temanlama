from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from .helpers import decorator
from .helpers import helpers
from bot.client import Bot
from bot.utils.coloredkb import btn
from bot.utils.coloredkb import ckb
from bot.utils.coloredkb import send_colored


@decorator.Admins
async def generate(client: Bot, message: Message):
    if not helpers.generate:
        # FIX: dulu di sini cuma `return None` tanpa balasan apapun, jadi
        # kelihatan seperti bot freeze/tidak respon padahal Generator
        # Controller memang masih OFF. Sekarang admin dikasih tahu jelas.
        await send_colored(
            client,
            message.chat.id,
            (
                '⚠️ <b>Generator masih OFF.</b>\n\n'
                'Pesan kamu tidak diproses jadi link karena fitur Generate '
                'belum diaktifkan.\n'
                'Aktifkan lewat: /set → <b>Generate Controller</b> → Change.'
            ),
        )
        return None

    dbchid = client.env.DATABASE_ID
    copied = await helpers.copymsg(message)
    encode = client.url.encode(
        f'id-{copied * abs(dbchid)}',
    )
    urlstr = helpers.urlstr(encode)
    urlmsg = f'https://t.me/c/{str(dbchid)[4:]}/{copied}'
    markup = ckb([
        [
            btn('Message', url=urlmsg, style='success'),
            btn('Share', url=helpers.urlstr(urlstr, share=True), style='primary'),
        ],
        [
            btn('📋 Copy Link', copy_text=urlstr),
        ],
    ])
    text = (
        '<blockquote><b>🔗 Link berhasil dibuat!</b>\n\n'
        'Bagikan ke orang lain lewat tombol di bawah, atau salin manual:\n\n'
        f'<code>{urlstr}</code></blockquote>'
    )
    await send_colored(
        client,
        message.chat.id,
        text,
        reply_markup=markup,
    )
    # Comment out or remove the following line to avoid deleting the user's message
    # return await message.delete()

Bot.add_handler(
    MessageHandler(
        generate,
        filters=~command(Bot.cmd.cmds) & private,
    ),
)
