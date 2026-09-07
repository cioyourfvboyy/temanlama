import sqlite3, os, signal, threading, time
from datetime import datetime, timedelta
from config import DB_PATH, OWNER_ID
from main import bot

# === DATABASE ===
def db_masa():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS bot_masa(
        kunci TEXT PRIMARY KEY, nilai TEXT)""")
    con.commit()
    con.close()

# === FUNGSI PENGATURAN ===
def atur_hari(hari):
    db_masa()
    waktu = (datetime.now() + timedelta(days=hari)).isoformat()
    con = sqlite3.connect(DB_PATH)
    con.execute("REPLACE INTO bot_masa VALUES('akhir',?)", (waktu,))
    con.commit()
    con.close()
    return f"✅ BERHASIL!\nMasa: {hari} hari\nSampai: {datetime.fromisoformat(waktu).strftime('%Y-%m-%d %H:%M')}"

def cek_waktu():
    db_masa()
    con = sqlite3.connect(DB_PATH)
    res = con.execute("SELECT nilai FROM bot_masa WHERE kunci='akhir'").fetchone()
    con.close()
    if not res: return "ℹ️ Belum diatur masa aktif"
    akhir = datetime.fromisoformat(res[0])
    skrg = datetime.now()
    if akhir < skrg: return "❌ Masa HABIS! Bot mati."
    sisa = akhir - skrg
    return f"⏳ MASA BOT\nSisa: {sisa.days} hari {sisa.seconds//3600} jam\nSampai: {akhir.strftime('%Y-%m-%d %H:%M')}"

def pantau_mati():
    while True:
        db_masa()
        con = sqlite3.connect(DB_PATH)
        res = con.execute("SELECT nilai FROM bot_masa WHERE kunci='akhir'").fetchone()
        con.close()
        if res:
            akhir = datetime.fromisoformat(res[0])
            if akhir < datetime.now():
                bot.send_message(OWNER_ID, "⚠️ MASA HABIS! BOT DIMATIKAN.")
                time.sleep(2)
                os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(60) # Cek tiap 1 menit

# === PERINTAH BOT ===
def daftar(bot):
    @bot.message_handler(commands=['masa'])
    def cek(msg): bot.reply_to(msg, cek_waktu())

    @bot.message_handler(commands=['tambah'])
    def tambah(msg):
        if msg.from_user.id != int(OWNER_ID):
            bot.reply_to(msg, "❌ Hanya Pemilik!")
            return
        try:
            hari = int(msg.text.split()[1])
            bot.reply_to(msg, atur_hari(hari))
        except:
            bot.reply_to(msg, "⚠️ Contoh: /tambah 30")

    # Mulai pantau latar belakang
    threading.Thread(target=pantau_mati, daemon=True).start()
