import time

import uvloop
from pyrogram import Client

from .utils.cache import Cache
from .utils.db import Database
from .utils.logger import Logger
from .utils.misc import Commands
from .utils.misc import URLSafe
from config import Config


class Bot(Client):
    log = Logger
    env = Config
    var = Cache
    cmd = Commands
    url = URLSafe
    mdb = Database
    start_time: float = 0.0  # diisi saat start() -> dipakai /kondisi buat uptime

    def __init__(self):
        name     = self.env.BOT_ID
        api_id   = self.env.API_ID
        api_hash = self.env.API_HASH
        bot_token = self.env.BOT_TOKEN

        super().__init__(
            name,
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token,
            # Tidak ada mongodb= — pakai SQLite sekarang
        )

    async def start(self):
        uvloop.install()
        await super().start()
        self.start_time = time.time()
        self.log.info(f'{self.me.id} Started')

    async def stop(self, *args):
        from .utils.botapi import BotAPI
        await BotAPI(self.env.BOT_TOKEN).close()
        await super().stop()
        self.log.warning('Client Stopped')


Bot = Bot()
