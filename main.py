import asyncio
import datetime
import functools
import os
import sys
import signal

from pyrogram.errors import RPCError
from pyrogram.types import BotCommand

from bot.client import Bot
from bot.utils.backup import send_db_backup
from plugins import loadplugin
from plugins.helpers import helpers


# ==============================================
# ✅ FITUR MASA AKTIF BOT (TAMBAHAN)
# ==============================================
DB_MASA_KEY = "BOT_AKHIR_MASA"

async def init_masa_db():
    """Buat penyimpanan masa aktif di database bot"""
    await Bot.mdb.init()

async def atur_masa_bot(hari: int) -> str:
    """Atur/perpanjang masa aktif bot"""
    await init_masa_db()
    sekarang = datetime.datetime.now()
    data = await Bot.mdb.gvars(DB_MASA_KEY)
    
    if data:
        akhir_lama = datetime.datetime.fromisoformat(data)
        if akhir_lama > sekarang:
            akhir_baru = akhir_lama + datetime.timedelta(days=hari)
        else:
            akhir_baru = sekarang + datetime.timedelta(days=hari)
    else:
        akhir_baru = sekarang + datetime.timedelta(days=hari)
    
    await Bot.mdb.invar(DB_MASA_KEY, "nilai", akhir_baru.isoformat())
    return f"""✅ **Masa Bot Diatur!**
⏳ Durasi: {hari} hari
📅 Berakhir: {akhir_baru.strftime('%Y-%m-%d %H:%M:%S')}"""

async def cek_masa_bot() -> str:
    """Cek sisa masa aktif bot"""
    await init_masa_db()
    data = await Bot.mdb.gvars(DB_MASA_KEY)
    sekarang = datetime.datetime.now()
    
    if not data or "nilai" not in data:
        return "ℹ️ **Belum Ada Masa Aktif**\nGunakan /tambahmasa [hari] untuk mengatur."
    
    akhir = datetime.datetime.fromisoformat(data["nilai"])
    if akhir < sekarang:
        return "❌ **Masa HABIS!**\nBot akan dimatikan otomatis."
    
    sisa = akhir - sekarang
    return f"""⏳ **STATUS MASA BOT**
✅ Sedang Aktif
📊 Sisa: {sisa.days} hari {sisa.seconds//3600} jam {(sisa.seconds%3600)//60} menit
📅 Berakhir: {akhir.strftime('%Y-%m-%d %H:%M:%S')}"""

async def pantau_masa_berjalan():
    """Cek terus-menerus, mati otomatis jika habis"""
    while True:
        pesan = await cek_masa_bot()
        if "HABIS" in pesan:
            await Bot.send_message(Bot.env.OWNER_ID, "⚠️ **PEMBERITAHUAN**\n⏰ Masa aktif bot TELAH HABIS!\n🔴 Bot dimatikan sekarang.")
            await Bot.stop()
            os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(60)  # Cek tiap 1 menit

async def daftar_perintah_masa():
    """Tambah perintah ke bot"""
    from bot.client import Bot

    @Bot.on_message(filters=filters.command("masa") & filters.user(Bot.env.OWNER_ID))
    async def _cek_masa(_, msg):
        await msg.reply_text(await cek_masa_bot())

    @Bot.on_message(filters=filters.command("tambahmasa") & filters.user(Bot.env.OWNER_ID))
    async def _tambah_masa(_, msg):
        if len(msg.command) < 2:
            await msg.reply_text("⚠️ Contoh: /tambahmasa 30")
            return
        try:
            hari = int(msg.command[1])
            if hari <= 0 or hari > 3650:
                raise ValueError
            await msg.reply_text(await atur_masa_bot(hari))
        except:
            await msg.reply_text("❌ Masukkan angka hari yang valid!")
# ==============================================
# ✅ SELESAI FITUR MASA
# ==============================================


async def main():
    # 1. Inisialisasi tabel SQLite
    await Bot.mdb.init()

    Bot.log.info('Starting Client')
    await starting()

    Bot.log.info('Initializing DatabaseID')
    await getdbcid()
    Bot.log.info('DatabaseID Initialized')

    Bot.log.info('Fetching SQLite Database')
    await Bot.var.fetching()

    Bot.log.info('Initializing Environment')
    await helpers.cached()

    # ✅ Aktifkan fitur masa & pantau
    Bot.log.info('Loading Fitur Masa Aktif')
    await daftar_perintah_masa()
    asyncio.create_task(pantau_masa_berjalan())

    Bot.log.info('Setting Bot Command')
    await botcmd()

    # 2. Pastikan nilai default ada di DB
    await dbctrl()

    Bot.log.info('Importing Plugins')
    loadplugin()

    Bot.log.info('Checking Restart Data')
    await rmsg('rmsg')
    await rmsg('bmsg')
    Bot.log.info('Restart Data Checked')

    # 3. Kirim backup DB ke LOG_DB_ID saat start/restart
    if Bot.env.LOG_DB_ID:
        Bot.log.info('Sending DB backup to LOG_DB_ID')
        await send_db_backup(
            Bot,
            Bot.env.LOG_DB_ID,
            '🔄 **Bot Started / Restarted**\n📦 Backup DB terlampir.',
        )

    # 4. Jadwalkan restart otomatis tiap jam 00:00 + kirim backup DB
    asyncio.create_task(daily_restart_scheduler())


async def daily_restart_scheduler():
    """Restart otomatis tiap jam 00:00 (waktu server) + kirim backup DB ke
    LOG_DB_ID terlebih dahulu — logikanya sama persis dengan command /r
    (lihat plugins/debug.py: restart()), cuma dipicu jadwal, bukan admin."""
    while True:
        now = datetime.datetime.now()
        next_midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        wait_seconds = (next_midnight - now).total_seconds()
        Bot.log.info(
            f'Daily restart dijadwalkan dalam {wait_seconds:.0f}s '
            f'(pukul 00:00 waktu server)',
        )
        await asyncio.sleep(wait_seconds)

        Bot.log.info('00:00 — Memulai daily backup & restart otomatis')
        if Bot.env.LOG_DB_ID:
            await send_db_backup(
                Bot,
                Bot.env.LOG_DB_ID,
                '🕛 **Daily Backup (00:00)**\n📦 Backup DB otomatis sebelum restart.',
            )

        # Truncate log lama (sama seperti /r)
        try:
            with open('log.txt', 'r+') as f:
                f.truncate(0)
        except FileNotFoundError:
            pass

        # Restart via os.execl agar event loop bersih (sama seperti /r).
        # FIX: pakai sys.executable (bukan hardcoded /usr/bin/python3) supaya
        # restart tetap pakai interpreter yang sama dengan yang sedang jalan
        # (mis. python venv). Kalau bot dijalankan dari venv tapi restart
        # paksa ke /usr/bin/python3 (python sistem tanpa pyrogram dkk
        # terinstall), bot langsung crash setelah restart/update.
        os.execl(sys.executable, sys.executable, os.path.abspath(__file__))


def rpchndlr(func):
    @functools.wraps(func)
    async def wrapper():
        try:
            return await func()
        except RPCError as e:
            Bot.log.error(str(e))
            sys.exit(1)
    return wrapper


@rpchndlr
async def starting():
    await Bot.start()


@rpchndlr
async def getdbcid():
    hellomsg = await Bot.send_message(Bot.env.DATABASE_ID, 'Hello World!')
    await hellomsg.delete()


async def dbctrl():
    bvar = await Bot.mdb.gvars('BOT_VARS')
    dvar = {
        'GEN_STATUS':      True,
        'PROTECT_CONTENT': True,
        'START_MESSAGE':   Bot.env.startmsg,
        'FORCE_MESSAGE':   Bot.env.forcemsg,
        'ADMIN_IDS':       Bot.env.OWNER_ID,
        'VIEW_ENABLED':    True,
        'VIEW_LIMIT':      30,
    }
    if not bvar:
        for key, value in dvar.items():
            await Bot.mdb.invar('BOT_VARS', key, value)


async def botcmd():
    await Bot.set_bot_commands([
        BotCommand(Bot.cmd.start,       'Mulai bot'),
        BotCommand(Bot.cmd.info,        'Informasi bot'),
        BotCommand(Bot.cmd.batch,       'Membuat batch media'),
        BotCommand(Bot.cmd.broadcast,   'Broadcast pesan (reply)'),
        BotCommand(Bot.cmd.autobc,      'Auto Broadcast dari Channel'),
        BotCommand(Bot.cmd.configs,     'Menu pengaturan bot'),
        BotCommand(Bot.cmd.health,      'Cek kondisi & kesiapan broadcast bot'),
        BotCommand(Bot.cmd.setcaption,  'Set caption otomatis di konten'),
        BotCommand(Bot.cmd.delcaption,  'Hapus caption otomatis'),
        BotCommand(Bot.cmd.getcaption,  'Cek caption otomatis aktif'),
        BotCommand(Bot.cmd.setpromo,    'Set link tombol PROMO VIP'),
        BotCommand(Bot.cmd.delpromo,    'Hapus link PROMO VIP'),
        BotCommand(Bot.cmd.getpromo,    'Cek link PROMO VIP aktif'),
        BotCommand(Bot.cmd.autodelete,  'Atur auto-delete konten'),
        BotCommand(Bot.cmd.view,        'Buka media acak dari database'),
        BotCommand(Bot.cmd.setview,     'Atur fitur /view (admin)'),
        BotCommand(Bot.cmd.backup,      'Backup database (zip)'),
        BotCommand(Bot.cmd.restore,     'Restore database dari zip'),
        BotCommand(Bot.cmd.update,      'Update kode dari repo & restart'),
        BotCommand(Bot.cmd.restart,     'Restart bot'),
        BotCommand(Bot.cmd.evaluate,    'Eval/jalankan kode (debug)'),
        BotCommand(Bot.cmd.log,         'Kirim file log'),
        BotCommand('masa',               'Cek masa aktif bot'),
        BotCommand('tambahmasa',         'Tambah masa aktif bot'),
    ])
    Bot.log.info('Bot Command Has Set')


async def rmsg(_id: str):
    data = await Bot.mdb.gmsgs(_id)
    if data:
        cid, mid = data['cid'], data['mid']
        await Bot.send_message(cid, 'Bot Restarted ✅', reply_to_message_id=mid)
        await Bot.mdb.rmmsg(_id)


if __name__ == '__main__':
    # ✅ Tambah import filters jika belum ada
    from pyrogram import filters
    asyncio.get_event_loop().run_until_complete(main())
    Bot.log.info('Bot Has Been Activated')
    Bot.loop.run_forever()
