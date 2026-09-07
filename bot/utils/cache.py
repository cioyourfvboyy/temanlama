from bot.utils.db import Database
from bot.utils.logger import Logger
from config import Config


class Cache:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.data = None

    async def fetching(self) -> None:
        self.clear()
        await self.relown()
        self.data = await self.gvars()
        Logger.info('SQLite Database Fetched')

    def clear(self) -> None:
        self.data = None

    async def gvars(self) -> dict:
        return await self.db.gvars('BOT_VARS') or {}

    async def admnvar(self) -> list:
        bvars = await self.gvars()
        return bvars.get('ADMIN_IDS', [])

    async def relown(self) -> None:
        owner = Config.OWNER_ID
        admns = await self.admnvar()
        if owner not in admns:
            await self.db.invar('BOT_VARS', 'ADMIN_IDS', owner)

    @property
    def vars(self) -> dict:
        return self.data or {}


Cache = Cache(Database)
