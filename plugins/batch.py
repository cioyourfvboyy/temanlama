import contextlib

from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.handlers import MessageHandler
from pyrogram.helpers import ikb
from pyrogram.types import Message

from .helpers import decorator
from .helpers import helpers
from bot.client import Bot
from bot.utils.coloredkb import btn
from bot.utils.coloredkb import ckb
from bot.utils.coloredkb import send_colored


@decorator.Admins
async def batch(client: Bot, message: Message):
    cid = message.chat.id
    uid = message.from_user.id
    cdb = client.env.DATABASE_ID

    async def ask(text, link):
        # NOTE: client.ask() adalah method Pyrofork/MTProto, ia membutuhkan
        # objek pyrogram.types.InlineKeyboardMarkup asli (punya .write()),
        # bukan dict mentah ala bot/utils/coloredkb — jadi di sini TETAP
        # pakai ikb() bawaan Pyrogram. Tombol ini hanya petunjuk sementara
        # (forward pesan), bukan bagian dari menu utama, sehingga warna
        # tidak krusial di sini.
        cask = await client.ask(
            chat_id=cid,
            text=text,
            user_id=uid,
            reply_markup=ikb([[('Database', link, 'url')]]),
        )
        await cask.sent_message.delete()
        if (
            not cask.forward_from_chat
            or cask.forward_from_chat.id != cdb
        ):
            await cask.reply('Invalid!', quote=True)
            return None
        return cask

    def dburl(msgid):
        return f'https://t.me/c/{str(cdb)[4:]}/{msgid}'

    await message.delete()

    fask = await ask(
        'Forward: First Message',
        f'tg://openmessage?chat_id={str(cdb)[4:]}',
    )
    if not fask:
        return
    first = fask.forward_from_message_id
    flink = dburl(first)
    await fask.delete()

    lask = await ask('Forward: Last Message', flink)
    if not lask:
        return
    last = lask.forward_from_message_id
    lurl = dburl(last)
    await lask.delete()

    with contextlib.suppress(ValueError):
        if (abs(int(first) - int(last)) + 1) > 200:
            return await message.reply(
                "Can't retrieve >200 messages.",
            )

    urlstr = helpers.urlstr(helpers.encode(first, last))
    # Hasil akhir dikirim lewat Bot API HTTP supaya tombolnya bisa berwarna.
    markup = ckb([
        [
            btn('First', url=flink),
            btn('Share', url=helpers.urlstr(urlstr, share=True)),
            btn('Last', url=lurl),
        ],
    ])
    await send_colored(
        client,
        message.chat.id,
        urlstr,
        reply_markup=markup,
    )


Bot.add_handler(
    MessageHandler(
        batch,
        filters=command(Bot.cmd.batch) & private,
    ),
)
