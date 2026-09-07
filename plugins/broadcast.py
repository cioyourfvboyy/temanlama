import asyncio
import contextlib
import time

from pyrogram.errors import FloodWait
from pyrogram.errors import RPCError
from pyrogram.errors import UserIsBlocked
from pyrogram.filters import command
from pyrogram.filters import create
from pyrogram.filters import regex
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.handlers import MessageHandler
from pyrogram.raw.functions import Ping
from pyrogram.types import CallbackQuery
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


gVarBcRun = False
gVarBcSent = 0
gVarBcFail = 0
gVarBcTotal = 0

CLOSE_MARKUP = ckb([[btn('Close', 'home-close', style='danger')]])


@decorator.Admins
async def broadcast(client: Bot, message: Message):
    global gVarBcRun
    global gVarBcSent
    global gVarBcFail
    global gVarBcTotal

    if not (bcmsg := message.reply_to_message):
        return await message.reply(
            'Reply to message.',
            quote=True,
        )

    if gVarBcRun:
        return await message.reply(
            'Currently broadcast is running.',
            quote=True,
        )

    users = await client.mdb.gusrs()
    admns = helpers.adminids
    users = [usr for usr in users if usr not in admns]

    gVarBcRun = True
    gVarBcSent = 0
    gVarBcFail = 0
    gVarBcTotal = len(users)

    start_time = time.time()

    # Kirim pesan status awal (pakai keyboard berwarna: Stop=danger, Ref.=default)
    msg_data = await send_colored(
        client,
        message.chat.id,
        make_status_text(0, 0, gVarBcTotal),
        reply_markup=Markup.BROADCAST_STATS,
    )
    msg_chat_id = msg_data['chat']['id']
    msg_id = msg_data['message_id']

    await client.mdb.inmsg('bmsg', message.chat.id, msg_id)

    # Task update progress bar real-time setiap 2 detik
    async def live_progress():
        while gVarBcRun:
            await asyncio.sleep(2)
            elapsed = time.time() - start_time
            with contextlib.suppress(Exception):
                await edit_colored(
                    client, msg_chat_id, msg_id,
                    text=make_status_text(gVarBcSent, gVarBcFail, gVarBcTotal, elapsed),
                    reply_markup=Markup.BROADCAST_STATS,
                )

    progress_task = asyncio.create_task(live_progress())

    client.log.info('Starting Broadcast')
    for usr in users:
        if not gVarBcRun:
            break
        try:
            await helpers.copymsgs(bcmsg, usr)
            gVarBcSent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            client.log.warning(str(e))
        except UserIsBlocked:
            await client.mdb.rmusr(usr)
            gVarBcFail += 1
            client.log.info(f'User {usr} blocked the bot, removed from DB.')
        except RPCError as e:
            await client.mdb.rmusr(usr)
            gVarBcFail += 1
            client.log.warning(f'RPCError for user {usr}: {e}')

    # Stop live progress task
    gVarBcRun = False
    progress_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await progress_task

    elapsed = time.time() - start_time

    # Hapus pesan status lama
    with contextlib.suppress(RPCError):
        await client.delete_messages(msg_chat_id, msg_id)

    # Kirim hasil akhir
    bar, percent = make_progress_bar(gVarBcSent, gVarBcFail, gVarBcTotal)
    await send_colored(
        client,
        message.chat.id,
        f'✅ **Broadcast Selesai!**\n\n'
        f'`{bar}`\n\n'
        f'✅ Terkirim  : `{gVarBcSent}`\n'
        f'❌ Gagal     : `{gVarBcFail}`\n'
        f'👥 Total     : `{gVarBcTotal}`\n'
        f'🕐 Durasi    : `{elapsed:.0f}s`',
        reply_markup=CLOSE_MARKUP,
    )

    gVarBcSent = 0
    gVarBcFail = 0
    gVarBcTotal = 0

    client.log.info('Broadcast Finished')
    await client.mdb.rmmsg('bmsg')


async def cbqbcstats(client: Bot, cbq: CallbackQuery):
    global gVarBcRun
    global gVarBcSent
    global gVarBcFail
    global gVarBcTotal

    data = cbq.data.split('-')[1]
    chat_id, msg_id = cbq.message.chat.id, cbq.message.id

    if data == 'refresh':
        with contextlib.suppress(RPCError):
            await edit_colored(
                client, chat_id, msg_id,
                text=make_status_text(gVarBcSent, gVarBcFail, gVarBcTotal),
                reply_markup=Markup.BROADCAST_STATS,
            )
    elif data == 'abort':
        await client.mdb.rmmsg('bmsg')
        gVarBcRun = False
        await edit_colored(
            client, chat_id, msg_id,
            text=(
                '🛑 **Broadcast Dibatalkan!**\n\n'
                f'✅ Terkirim  : `{gVarBcSent}`\n'
                f'❌ Gagal     : `{gVarBcFail}`\n'
                f'👥 Total     : `{gVarBcTotal}`'
            ),
            reply_markup=CLOSE_MARKUP,
        )


@decorator.Admins
async def cbqstats(client: Bot, cbq: CallbackQuery):
    global gVarBcRun
    global gVarBcSent
    global gVarBcFail
    global gVarBcTotal

    users = await client.mdb.gusrs()
    data = cbq.data.split('-')[1]
    if data == 'ping':
        start = time.time()
        await client.invoke(Ping(ping_id=0))
        laten = f'{(time.time() - start) * 1000:.2f}ms'
        await cbq.answer(f'Pong! {laten}', show_alert=True)
    if data == 'users':
        await cbq.answer(
            f'Total: {len(users)} Users',
            show_alert=True,
        )
    if data == 'bc':
        if not gVarBcRun:
            return await cbq.answer(
                'No Broadcast is Running!',
                show_alert=True,
            )
        bar, percent = make_progress_bar(gVarBcSent, gVarBcFail, gVarBcTotal)
        await cbq.answer(
            f'📡 Broadcast Status\n'
            f'{bar}\n'
            f'Sent: {gVarBcSent} | Failed: {gVarBcFail} | Total: {gVarBcTotal}',
            show_alert=True,
        )


ChatTypeGROUP = create(
    lambda _, __,
    message: message.chat.type.value == 'group',
)

Bot.add_handler(
    MessageHandler(
        broadcast,
        filters=command(Bot.cmd.broadcast) &
        ~ChatTypeGROUP,
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cbqbcstats,
        filters=regex(r'^bc'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cbqstats,
        filters=regex(r'^stats'),
    ),
)
