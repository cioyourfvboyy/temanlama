"""
Debug & maintenance commands:
  /log      — kirim log.txt
  /e <code> — eval python
  /r        — restart bot (kirim backup DB dulu ke LOG_DB_ID)
  /backup   — kirim zip DB sekarang
  /restore  — reply zip → restore DB & restart
  /update   — git pull + restart
"""
import asyncio
import io
import os
import subprocess
import sys

from meval import meval
from pyrogram.filters import command
from pyrogram.filters import private
from pyrogram.filters import user
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from bot.client import Bot
from bot.utils.backup import create_backup_zip, restore_from_zip, send_db_backup


# ---------------------------------------------------------------------------
# /log
# ---------------------------------------------------------------------------
async def log(_, message: Message):
    await message.reply_document('log.txt', quote=True)


# ---------------------------------------------------------------------------
# /e — eval
# ---------------------------------------------------------------------------
async def evaluate(client: Bot, message: Message):
    if len(message.command) == 1:
        return await message.reply(
            "<pre language='python'>None</pre>", quote=True
        )

    msg  = await message.reply('...', quote=True)
    code = message.text.split(maxsplit=1)[1]
    output = '<b>Output: </b>'
    Bot.log.info(f'Eval-In: {code}')

    evars = {
        'c': client,
        'm': message,
        'r': message.reply_to_message,
        'u': (message.reply_to_message or message).from_user,
    }

    def _print(*args, **kwargs):
        buf = io.StringIO()
        print(*args, file=buf, **kwargs)
        return buf.getvalue()

    evars['print'] = _print

    try:
        result = await meval(code, globals(), **evars)
        output += f"<pre language='python'>{result}</pre>"
        Bot.log.info(f'Eval-Out: {result}')
    except Exception as e:
        Bot.log.info(f'Eval-Out: {e}')
        return await msg.edit(
            f'<b>Output:\n</b><pre language="python">{e}</pre>'
        )

    if len(output) > 4096:
        with open('output.txt', 'w') as w:
            w.write(str(result))
        await message.reply_document('output.txt', quote=True)
        os.remove('output.txt')
        return await msg.delete()

    await msg.edit(text=output)


# ---------------------------------------------------------------------------
# /r — restart
# ---------------------------------------------------------------------------
async def restart(client: Bot, message: Message):
    msg = await message.reply('⏳ Restarting...')

    # Simpan info pesan agar diedit setelah restart
    await client.mdb.inmsg('rmsg', message.chat.id, msg.id)

    # Kirim backup DB ke LOG_DB_ID sebelum restart
    if client.env.LOG_DB_ID:
        await send_db_backup(
            client,
            client.env.LOG_DB_ID,
            '🔄 **Bot Restart** — backup DB sebelum restart.',
        )

    await message.delete()

    # Truncate log lama
    with open('log.txt', 'r+') as f:
        f.truncate(0)

    # Restart via os.execl agar event loop bersih
    os.execl(sys.executable, sys.executable, os.path.abspath('main.py'))


# ---------------------------------------------------------------------------
# /backup — kirim zip DB sekarang
# ---------------------------------------------------------------------------
async def backup(client: Bot, message: Message):
    msg = await message.reply('⏳ Membuat backup...')
    try:
        zip_bytes = create_backup_zip()
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'db_backup_{ts}.zip'
        buf = io.BytesIO(zip_bytes)
        buf.name = filename
        await message.reply_document(
            buf,
            caption=f'📦 **Database Backup**\n`{filename}`',
            file_name=filename,
        )
        await msg.delete()
    except Exception as e:
        await msg.edit(f'❌ Gagal backup: `{e}`')


# ---------------------------------------------------------------------------
# /restore — reply dengan file .zip untuk restore DB
# ---------------------------------------------------------------------------
async def restore(client: Bot, message: Message):
    replied = message.reply_to_message
    if not replied or not replied.document:
        return await message.reply(
            '⚠️ Reply file zip backup untuk restore.\nContoh: reply file zip lalu /restore',
            quote=True,
        )

    if not replied.document.file_name.endswith('.zip'):
        return await message.reply('❌ File harus berformat `.zip`', quote=True)

    msg = await message.reply('⏳ Mengunduh & restore database...')
    try:
        buf = await client.download_media(replied, in_memory=True)
        restore_from_zip(bytes(buf.getbuffer()))
        await msg.edit('✅ Database berhasil di-restore!\n🔄 Bot akan restart sekarang...')

        # Simpan pending message restart
        await client.mdb.inmsg('rmsg', message.chat.id, msg.id)

        # Restart
        os.execl(sys.executable, sys.executable, os.path.abspath('main.py'))
    except Exception as e:
        await msg.edit(f'❌ Restore gagal: `{e}`')


# ---------------------------------------------------------------------------
# /update — git pull + restart
# ---------------------------------------------------------------------------
async def update(client: Bot, message: Message):
    msg = await message.reply('⏳ Mengambil update dari repo...')

    try:
        result = subprocess.run(
            ['git', 'pull'],
            capture_output=True,
            text=True,
            timeout=60,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        output = stdout or stderr or 'Tidak ada output dari git.'

        if result.returncode != 0:
            return await msg.edit(
                f'❌ **git pull gagal**\n\n```\n{output}\n```'
            )

        await msg.edit(
            f'✅ **Update berhasil!**\n\n```\n{output}\n```\n\n'
            '🔄 Bot akan restart dalam 3 detik...'
        )
        await asyncio.sleep(3)

        # Backup DB sebelum restart
        if client.env.LOG_DB_ID:
            await send_db_backup(
                client,
                client.env.LOG_DB_ID,
                '📦 Backup DB sebelum update & restart.',
            )

        # Simpan pending message restart
        await client.mdb.inmsg('rmsg', message.chat.id, msg.id)

        # Truncate log
        with open('log.txt', 'r+') as f:
            f.truncate(0)

        # Restart dengan kode baru
        os.execl(sys.executable, sys.executable, os.path.abspath('main.py'))

    except subprocess.TimeoutExpired:
        await msg.edit('❌ git pull timeout (>60s). Cek koneksi server.')
    except FileNotFoundError:
        await msg.edit('❌ `git` tidak ditemukan di server. Install dulu: `sudo apt install git`')
    except Exception as e:
        await msg.edit(f'❌ Error: `{e}`')


# ---------------------------------------------------------------------------
# Handler registration — hanya owner
# ---------------------------------------------------------------------------
_owner = user(Bot.env.OWNER_ID)
_priv  = private

Bot.add_handler(MessageHandler(log,       command(Bot.cmd.log)      & _priv & _owner))
Bot.add_handler(MessageHandler(evaluate,  command(Bot.cmd.evaluate) & _priv & _owner))
Bot.add_handler(MessageHandler(restart,   command(Bot.cmd.restart)  & _priv & _owner))
Bot.add_handler(MessageHandler(backup,    command(Bot.cmd.backup)   & _priv & _owner))
Bot.add_handler(MessageHandler(restore,   command(Bot.cmd.restore)  & _priv & _owner))
Bot.add_handler(MessageHandler(update,    command(Bot.cmd.update)   & _priv & _owner))
