from html import escape as html_escape

from pyrogram import enums
from pyrogram.errors import RPCError
from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.filters import regex
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.handlers import MessageHandler
from pyrogram.types import CallbackQuery
from pyrogram.types import Message

from .helpers import decorator
from .helpers import helpers
from .helpers import Markup
from bot.client import Bot
from bot.utils.coloredkb import edit_colored
from bot.utils.coloredkb import send_colored
from bot.utils.coloredkb import premium_emoji


@decorator.Admins
async def configs(client: Bot, message: Message):
    await send_colored(
        client,
        message.chat.id,
        f'{premium_emoji("config", "⚙️")} <b>Bot Configuration Menu:</b>',
        reply_markup=Markup.HOME,
    )
    await message.delete()


@decorator.Admins
async def cbqhome(client: Bot, cbq: CallbackQuery):
    data = cbq.data.split('-')[1]
    chat_id, msg_id = cbq.message.chat.id, cbq.message.id

    async def do_close():
        await cbq.message.delete()

    async def do_home():
        await edit_colored(
            client, chat_id, msg_id,
            text=(
                f'{premium_emoji("config", "⚙️")} <b>Configuration:</b>\n\n'
                '/start - memulai bot\n'
                '/batch - membuat batch media\n'
                '/bc - broadcast pesan dengan replay\n'
                '/autobc &lt;id&gt; - daftarkan channel untuk auto broadcast\n'
                '/set - membuat pengaturan\n'
            ),
            reply_markup=Markup.HOME,
        )

    async def do_stats():
        await edit_colored(
            client, chat_id, msg_id,
            text='Monitor and Stats:',
            reply_markup=Markup.STATS,
        )

    action = {
        'close': do_close,
        'home': do_home,
        'stats': do_stats,
    }
    if action := action.get(data):
        await action()


@decorator.Admins
async def cbqset(client: Bot, cbq: CallbackQuery):
    bvar = client.var.vars
    data = cbq.data.split('-')[1]
    chat_id, msg_id = cbq.message.chat.id, cbq.message.id

    def format_list(title, items):
        if items:
            fmtitems = ''.join(
                f'  {i + 1}. `{item}`\n' for i,
                item in enumerate(items)
            )
        else:
            fmtitems = '  `None`'
        return f'{title}:\n{fmtitems}'

    def format_fsub_list(items):
        # Beda dari format_list biasa: tiap FSub ID disertai nama channel/grup
        # dan invite link-nya (diambil dari cache helpers.cached(), bukan
        # fetch baru ke Telegram tiap kali menu ini dibuka).
        if not items:
            return 'List FSub IDs:\n  <code>None</code>'
        lines = []
        for i, cid in enumerate(items, start=1):
            entry = helpers.cacheids.get(cid)
            if entry and entry.get('ilink'):
                title = html_escape(entry.get('title') or str(cid))
                lines.append(
                    f'  {i}. <a href="{entry["ilink"]}">{title}</a> — <code>{cid}</code>',
                )
            else:
                lines.append(
                    f'  {i}. <code>{cid}</code> — ⚠️ nama/link tidak tersedia '
                    '(bot mungkin bukan admin, di-kick, atau di-ban di sini)',
                )
        return 'List FSub IDs:\n' + '\n'.join(lines)

    # FIX: Gunakan default [False] agar tidak IndexError saat list kosong
    gprtct = bvar.get('PROTECT_CONTENT', [False])[0]
    ggnrte = bvar.get('GEN_STATUS', [False])[0]

    async def do_admnids():
        await edit_colored(
            client, chat_id, msg_id,
            text=format_list('List Admin IDs', bvar.get('ADMIN_IDS', [])),
            reply_markup=Markup.SET_ADMIN,
        )

    async def do_fscids():
        await edit_colored(
            client, chat_id, msg_id,
            text=format_fsub_list(bvar.get('FSUB_IDS', [])),
            reply_markup=Markup.SET_FSUB,
        )

    async def do_prtctcntnt():
        await edit_colored(
            client, chat_id, msg_id,
            text=f'Protect Content: {gprtct}',
            reply_markup=Markup.SET_PROTECT,
        )

    async def do_gen():
        await edit_colored(
            client, chat_id, msg_id,
            text=f'Generator: {ggnrte}',
            reply_markup=Markup.SET_GENERATOR,
        )

    async def do_strtmsg():
        await edit_colored(
            client, chat_id, msg_id,
            text=(
                'Start Text:\n  '
                f'<code>{bvar.get("START_MESSAGE", [""])[0].replace("<", "&lt;").replace(">", "&gt;")}</code>'
            ),
            reply_markup=Markup.SET_START,
            parse_mode='HTML',
        )

    async def do_frcmsg():
        await edit_colored(
            client, chat_id, msg_id,
            text=(
                'Force Text:\n  '
                f'<code>{bvar.get("FORCE_MESSAGE", [""])[0].replace("<", "&lt;").replace(">", "&gt;")}</code>'
            ),
            reply_markup=Markup.SET_FORCE,
            parse_mode='HTML',
        )

    action = {
        'admnids': do_admnids,
        'fscids': do_fscids,
        'prtctcntnt': do_prtctcntnt,
        'gen': do_gen,
        'strtmsg': do_strtmsg,
        'frcmsg': do_frcmsg,
    }
    if action := action.get(data):
        await action()


@decorator.Admins
async def cbqstats(client: Bot, cbq: CallbackQuery):
    # FIX: Handler baru untuk tombol Broadcast, Ping, Users di menu Stats
    data = cbq.data.split('-')[1]
    chat_id, msg_id = cbq.message.chat.id, cbq.message.id

    if data == 'ping':
        from pyrogram.raw.functions import Ping as RawPing
        import time
        start = time.time()
        await client.invoke(RawPing(ping_id=0))
        elapsed = (time.time() - start) * 1000
        await edit_colored(
            client, chat_id, msg_id,
            text=f'🏓 Pong!\n⚡ Latency: `{elapsed:.2f} ms`',
            reply_markup=Markup.BACK,
        )

    elif data == 'users':
        users = await client.mdb.gusrs()
        total = len(users) if users else 0
        await edit_colored(
            client, chat_id, msg_id,
            text=f'👥 Total Users: `{total}`',
            reply_markup=Markup.BACK,
        )

    elif data == 'bc':
        await edit_colored(
            client, chat_id, msg_id,
            text='Gunakan perintah /bc untuk memulai broadcast.',
            reply_markup=Markup.BACK,
        )


@decorator.Admins
async def cbqchange(client: Bot, cbq: CallbackQuery):
    chat_id, msg_id = cbq.message.chat.id, cbq.message.id

    async def replace(field, new):
        await client.mdb.outvars('BOT_VARS', field)
        await client.mdb.invar('BOT_VARS', field, new)
        await client.var.fetching()
        await helpers.cached()

    bvar = client.var.vars
    data = cbq.data.split('-')[1]

    if data in ['prtctcntnt', 'gen']:
        field = (
            'PROTECT_CONTENT' if data == 'prtctcntnt'
            else 'GEN_STATUS'
        )
        # FIX: Gunakan default [False] agar tidak IndexError
        crrnt = bvar.get(field, [False])[0]
        await replace(field, not crrnt)
        smsg = (
            'Protect Content' if data == 'prtctcntnt'
            else 'Generator'
        )
        await edit_colored(
            client, chat_id, msg_id,
            text=smsg + ' Changed',
            reply_markup=Markup.BACK,
        )
    elif data in ['strtmsg', 'frcmsg']:
        mtype = 'Start' if data == 'strtmsg' else 'Force'
        await edit_colored(client, chat_id, msg_id, text=f'Send {mtype} Text')
        lstn = await client.listen(
            user_id=cbq.message.chat.id,
        )
        await lstn.delete()
        if not lstn or not lstn.text:
            return await edit_colored(
                client, chat_id, msg_id,
                text='Invalid! Just Send a Text',
                reply_markup=Markup.SET_START,
            )
        field = 'START_MESSAGE' if data == 'strtmsg' else 'FORCE_MESSAGE'
        await replace(field, lstn.text)
        await edit_colored(
            client, chat_id, msg_id,
            text=f'{mtype} Text:\n  `{lstn.text}`',
            reply_markup=Markup.BACK,
        )


@decorator.Admins
async def cbqadd(client: Bot, cbq: CallbackQuery):
    chat_id, msg_id = cbq.message.chat.id, cbq.message.id

    async def addvar(field, new):
        await client.mdb.invar(
            'BOT_VARS',
            field,
            new,
        )
        await client.var.fetching()
        await helpers.cached()

    bvar = client.var.vars
    data = cbq.data.split('-')[1]
    enti = 'Admin' if data == 'admnids' else 'FSub'
    vari = 'ADMIN_IDS' if data == 'admnids' else 'FSUB_IDS'
    set_markup = Markup.SET_ADMIN if data == 'admnids' else Markup.SET_FSUB

    await edit_colored(
        client, chat_id, msg_id,
        text=f'Send {"User" if enti == "Admin" else "Chat"} ID to Add {enti}',
    )
    lstn = await client.listen(
        user_id=cbq.message.chat.id,
    )
    await lstn.delete()
    if lstn and not lstn.text:
        return await edit_colored(
            client, chat_id, msg_id,
            text=f'Invalid! Just Send a {"User" if enti == "Admin" else "Chat"} ID',
            reply_markup=set_markup,
        )
    try:
        enid = int(lstn.text)
    except ValueError:
        return await edit_colored(
            client, chat_id, msg_id,
            text=f'Invalid! Just Send a {"User" if enti == "Admin" else "Chat"} ID',
            reply_markup=set_markup,
        )
    if enid in bvar.get(vari, []):
        return await edit_colored(
            client, chat_id, msg_id,
            text=f'{"User" if enti == "Admin" else "Chat"} ID Already Exists',
            reply_markup=set_markup,
        )
    await edit_colored(client, chat_id, msg_id, text='Initializing...')
    try:
        if data == 'admnids':
            await client.get_users(enid)
        else:
            (await client.get_chat(enid)).invite_link
    except RPCError:
        return await edit_colored(
            client, chat_id, msg_id,
            text=f'Invalid! {"User" if enti == "Admin" else "Chat"} ID Not Found',
            reply_markup=set_markup,
        )
    await addvar(vari, enid)
    await edit_colored(
        client, chat_id, msg_id,
        text=f'Added {enti}: `{enid}`',
        reply_markup=Markup.BACK,
    )


@decorator.Admins
async def cbqdel(client: Bot, cbq: CallbackQuery):
    chat_id, msg_id = cbq.message.chat.id, cbq.message.id

    async def delvar(field, newkey):
        await client.mdb.rmvar(
            'BOT_VARS',
            field,
            newkey,
        )
        await client.var.fetching()
        await helpers.cached()

    bvar = client.var.vars
    data = cbq.data.split('-')[1]
    enti = 'Admin' if data == 'admnids' else 'FSub'
    vari = 'ADMIN_IDS' if data == 'admnids' else 'FSUB_IDS'
    set_markup = Markup.SET_ADMIN if data == 'admnids' else Markup.SET_FSUB

    await edit_colored(
        client, chat_id, msg_id,
        text=f'Send {enti} ID to Delete {enti}',
    )
    lstn = await client.listen(
        user_id=cbq.message.chat.id,
    )
    await lstn.delete()
    if lstn and not lstn.text:
        return await edit_colored(
            client, chat_id, msg_id,
            text=f'Invalid! Just Send a {"User" if enti == "Admin" else "Chat"} ID',
            reply_markup=set_markup,
        )
    try:
        enid = int(lstn.text)
    except ValueError:
        return await edit_colored(
            client, chat_id, msg_id,
            text=f'Invalid! Just Send a {"User" if enti == "Admin" else "Chat"} ID',
            reply_markup=set_markup,
        )
    if enid not in bvar.get(vari, []):
        return await edit_colored(
            client, chat_id, msg_id,
            text=f'Invalid! {"User" if enti == "Admin" else "Chat"} ID Not Found',
            reply_markup=set_markup,
        )
    if enid == cbq.message.chat.id:
        return await edit_colored(
            client, chat_id, msg_id,
            text="No Rights! That's You",
            reply_markup=set_markup,
        )
    await delvar(vari, enid)
    await edit_colored(
        client, chat_id, msg_id,
        text=f'Deleted {enti}: `{enid}`',
        reply_markup=Markup.BACK,
    )


Bot.add_handler(
    MessageHandler(
        configs,
        filters=command(Bot.cmd.configs) & private,
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cbqhome,
        filters=regex(r'^home'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cbqset,
        filters=regex(r'^set'),
    ),
)
# FIX: Tambah handler untuk tombol stats (Broadcast, Ping, Users)
Bot.add_handler(
    CallbackQueryHandler(
        cbqstats,
        filters=regex(r'^stats'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cbqchange,
        filters=regex(r'^change'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cbqadd,
        filters=regex(r'^add'),
    ),
)
Bot.add_handler(
    CallbackQueryHandler(
        cbqdel,
        filters=regex(r'^del'),
    ),
)
