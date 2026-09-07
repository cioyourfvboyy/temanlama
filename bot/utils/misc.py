import base64


class URLSafe:
    @staticmethod
    def addpad(data: str) -> str:
        return data + '=' * (-len(data) % 4)

    @staticmethod
    def delpad(data: str) -> str:
        return data.rstrip('=')

    def encode(self, data: str) -> str:
        encoded = base64.urlsafe_b64encode(data.encode('utf-8'))
        return self.delpad(encoded.decode('utf-8'))

    def decode(self, data: str) -> str:
        padded = self.addpad(data)
        decoded = base64.urlsafe_b64decode(padded)
        return decoded.decode('utf-8')


URLSafe = URLSafe()


class Commands:
    cmds: list[str] = []

    def __init__(self):
        self.start    = 'start'
        self.info     = 'info'
        self.batch    = 'batch'
        self.broadcast = 'bc'
        self.configs  = 'set'
        self.autobc   = 'autobc'
        self.health   = 'health'
        self.log      = 'log'
        self.evaluate = 'e'
        self.restart  = 'r'
        self.backup   = 'backup'
        self.restore  = 'restore'
        self.update   = 'update'
        self.setcaption   = 'setcaption'
        self.delcaption   = 'delcaption'
        self.getcaption   = 'getcaption'
        self.setpromo     = 'setpromo'
        self.delpromo     = 'delpromo'
        self.getpromo     = 'getpromo'
        self.autodelete   = 'autodelete'
        self.setdev       = 'setdev'
        self.deldev       = 'deldev'
        self.getdev       = 'getdev'
        self.setstore     = 'setstore'
        self.delstore     = 'delstore'
        self.getstore     = 'getstore'
        self.view         = 'view'
        self.setview      = 'setview'
        self.setquotatext = 'setquotatext'
        self.getquota     = 'getquota'
        for attr, value in vars(self).items():
            if isinstance(value, str):
                self.cmds.append(value)


Commands = Commands()
