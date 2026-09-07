from dotenv import load_dotenv
import os

load_dotenv()


class Config:
    startmsg = (
        '<b>[Hallo 🙋 ganteng / cantik](https://graph.org/file/78bb59e8e07526dba87d7-4a45d642bbdab0ba7e.jpg) </b> \n\n'
        '<b>⁉️ Anda harus bergabung di Channel/Group terlebih dahulu untuk melihat file yang saya bagikan.\n\n☎️ Jika bot error Hub @laporankendala_Xbot. <b/>'
    )
    forcemsg = (
        '<b>[Hallo 🙋 ganteng / cantik](https://graph.org/file/78bb59e8e07526dba87d7-4a45d642bbdab0ba7e.jpg) </b> \n\n'
        '<b>⁉️ Anda harus bergabung di Channel/Group terlebih dahulu untuk melihat file yang saya bagikan.\n\n☎️ Jika bot error Hub @laporankendala_Xbot. <b/>'
    )

    OWNER_ID   = int(os.environ.get('OWNER_ID', '5918905984'))
    BOT_TOKEN  = os.environ.get('BOT_TOKEN', '7122721477:AAEJPdnjBw6YhjgNh-7fRmIaHXdQIv-21Yo')
    DATABASE_ID = int(os.environ.get('DATABASE_ID', '-1003877395507'))
    # Channel/group tempat backup DB dikirim otomatis saat restart
    LOG_DB_ID  = int(os.environ.get('LOG_DB_ID', '-1003877395507'))

    API_ID   = int(os.environ.get('API_ID', '20409913'))
    API_HASH = os.environ.get('API_HASH', '7e5b7eb079ab46d84cde424962b020a0')
    BOT_ID   = BOT_TOKEN.split(':', 1)[0] if BOT_TOKEN else 'bot'

    # Path file SQLite
    DB_PATH  = os.environ.get('DB_PATH', 'data/bot.db')


Config = Config()
