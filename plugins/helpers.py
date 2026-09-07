import asyncio
import contextlib
import functools

from pyrogram.errors import RPCError
from pyrogram.types import Message

from bot.utils.coloredkb import btn
from bot.utils.coloredkb import pbtn
from bot.utils.coloredkb import ckb
from bot.utils.coloredkb import edit_colored
from bot.utils.coloredkb import send_colored


# ---------------------------------------------------------------------------
# Broadcast progress helpers (dipakai oleh broadcast.py dan autobc.py)
# ---------------------------------------------------------------------------

def make_progress_bar(sent: int, fail: int, total: int, bar_length: int = 10):
    """Generate a battery-style horizontal progress bar."""
    if total == 0:
        percent = 0.0
    else:
        percent = (sent + fail) / total * 100

    filled = int((sent + fail) / total * bar_length) if total > 0 else 0
    empty = bar_length - filled
    bar = '█' * filled + '░' * empty
    battery = f'[{bar}] {percent:.1f}%'
    return battery, percent


def make_status_text(
    sent: int,
    fail: int,
    total: int,
    elapsed: float | None = None,
    title: str = '📡 **Broadcast Sedang Berjalan...**',
) -> str:
    """Build the full broadcast status message."""
    bar, percent = make_progress_bar(sent, fail, total)
    done = sent + fail
    remaining = total - done

    lines = [
        f'{title}\n',
        f'`{bar}`\n',
        f'✅ Terkirim  : `{sent}`',
        f'❌ Gagal     : `{fail}`',
        f'👥 Total     : `{total}`',
        f'⏳ Sisa      : `{remaining}`',
        f'📊 Progress  : `{percent:.1f}%`',
    ]
    if elapsed is not None:
        lines.append(f'🕐 Waktu     : `{elapsed:.0f}s`')
    return '\n'.join(lines)

from bot.client import Bot


class Helpers:
    cacheids = {}
    protectc: bool = False
    generate: bool = False
    adminids: list[int | None] = []
    fsubcids: list[int | None] = []
    autobcids: list[int | None] = []
    startmsg: str = ''
    forcemsg: str = ''
    captiontext: str = ''
    promolink: str = ''
    autodelete_raw: str | int | None = None
    devusername: str = ''
    storeusername: str = ''
    view_enabled: bool = True
    view_limit: int = 3
    quota_text: str = ''

    def __init__(self, Client: Bot):
        self._client_ = Client

    def gvars(self, vari: str) -> list:
        return self._client_.var.vars.get(vari)

    def initializing(self):
        self.adminids = self.gvars('ADMIN_IDS') or []
        self._client_.log.info('Admins Initialized')
        self.fsubcids = self.gvars('FSUB_IDS') or []
        self.autobcids = self.gvars('AUTOBC_IDS') or []
        self._client_.log.info(f'AutoBC IDs: {self.autobcids}')
        # FIX: Gunakan default [False] agar tidak IndexError jika belum ada di DB
        protect_val = self.gvars('PROTECT_CONTENT') or [False]
        self.protectc = protect_val[0]
        self._client_.log.info(f'Protect: {self.protectc}')
        # FIX: Gunakan default [''] agar tidak IndexError jika belum ada di DB
        start_val = self.gvars('START_MESSAGE') or ['']
        self.startmsg = start_val[0]
        self._client_.log.info('Start Text Initialized')
        # FIX: Gunakan default [''] agar tidak IndexError jika belum ada di DB
        force_val = self.gvars('FORCE_MESSAGE') or ['']
        self.forcemsg = force_val[0]
        self._client_.log.info('Force Text Initialized')
        # FIX: Gunakan default [False] agar tidak IndexError jika belum ada di DB
        gen_val = self.gvars('GEN_STATUS') or [False]
        self.generate = gen_val[0]
        self._client_.log.info(f'Generate: {self.generate}')
        # Caption otomatis di bawah konten (mirip fitur /setcaption fsub2)
        caption_val = self.gvars('CAPTION_TEXT') or ['']
        self.captiontext = caption_val[0]
        # Link tombol PROMO VIP di konten (mirip fitur /setpromo fsub2)
        promo_val = self.gvars('PROMO_LINK') or ['']
        self.promolink = promo_val[0]
        # Durasi auto-delete konten (mirip fitur /autodelete fsub2).
        # None = belum pernah diset (pakai default), 'off' = dimatikan
        # eksplisit, int/str angka = durasi dalam detik.
        autodel_val = self.gvars('AUTO_DELETE_DELAY') or [None]
        self.autodelete_raw = autodel_val[0]
        # Username developer & store bot, dipakai di /info (mirip fitur
        # /setcaption & /setpromo — bisa diubah owner/admin lewat
        # /setdev & /setstore tanpa perlu ubah kode).
        dev_val = self.gvars('DEV_USERNAME') or ['']
        self.devusername = dev_val[0]
        store_val = self.gvars('STORE_USERNAME') or ['']
        self.storeusername = store_val[0]
        # Fitur /view & tombol "📂 Buka Media" (plugins/view.py).
        # VIEW_ENABLED: on/off fitur (default True/ON kalau belum diset).
        view_en_val = self.gvars('VIEW_ENABLED') or [True]
        self.view_enabled = bool(view_en_val[0])
        # VIEW_LIMIT: kuota /view HARIAN per-member (bukan jumlah sampel
        # scan — itu konstan, lihat VIEW_SCAN_SIZE di plugins/view.py).
        # Ini persis semantik VIEW_LIMIT di bot asli Kingsuga: tiap klik
        # tombol angka di /view memakai 1 kuota, direset tiap ganti hari.
        # Default 3x/hari kalau belum pernah diset (sama seperti Kingsuga).
        view_lim_val = self.gvars('VIEW_LIMIT') or [3]
        try:
            self.view_limit = int(view_lim_val[0])
        except (TypeError, ValueError):
            self.view_limit = 3
        # Teks custom notice saat kuota /view habis (opsional, /setquotatext).
        # Kalau belum diset, pakai teks default ala Kingsuga (lihat
        # Helpers.quota_notice_text()).
        quota_txt_val = self.gvars('QUOTA_TEXT') or ['']
        self.quota_text = quota_txt_val[0]

    def urlikb(self, text: str, url: str, style: str | None = None) -> dict:
        """Markup berwarna (dict). Kirim lewat send_colored()/edit_colored(),
        BUKAN lewat method Pyrofork murni seperti client.send_message() atau
        client.ask(), karena keduanya butuh objek pyrogram.types asli."""
        return ckb([[btn(text, url=url, style=style)]])

    def urlstr(self, url: str, share=False) -> str:
        if share:
            return f'https://t.me/share/url?url={url}'
        return (
            'https://t.me/'
            f'{self._client_.me.username}?start={url}'
        )

    def clear(self):
        self.cacheids = {}

    def reload(self) -> dict:
        self.clear()
        return self.initializing()

    async def cached(self) -> dict:
        self.reload()
        if not self.fsubcids:
            return None
        for i, cid in enumerate(self.fsubcids):
            try:
                gchat = await self._client_.get_chat(cid)
                ctype = gchat.type.value
                title = 'Group' if ctype in [
                    'group',
                    'supergroup',
                ] else 'Channel'
                # FIX: gchat.invite_link cuma keisi kalau channel/grup PRIVATE
                # (atau bot sudah pernah generate invite link). Untuk channel/
                # grup PUBLIC (punya username), Telegram TIDAK mengisi field
                # ini -> ilink jadi None -> tombol Join hilang total di
                # usrikb()/admikb() walau user belum join (root cause laporan
                # "tombol join fsub tidak ada padahal belum join").
                # Fallback: pakai link t.me/username kalau public, atau coba
                # export invite link kalau private & bot adalah admin.
                ilink = gchat.invite_link
                if not ilink:
                    if gchat.username:
                        ilink = f'https://t.me/{gchat.username}'
                    else:
                        try:
                            ilink = await self._client_.export_chat_invite_link(cid)
                        except RPCError as ie:
                            ilink = None
                            self._client_.log.warning(
                                f'FSubID-{i + 1}: gagal generate invite link ({ie}). '
                                'Pastikan bot adalah ADMIN di channel/grup ini.',
                            )
                self.cacheids[cid] = {
                    'title': title,
                    'ilink': ilink,
                }
                self._client_.log.info(f'FSubID-{i + 1} Initialized')
            except RPCError as e:
                self._client_.log.warning(f'FSubID-{i + 1}: {e}')

    async def usrikb(
        self,
        message: Message,
        user: int,
        nojoin_list: list[int] | None = '__unset__',
    ) -> None:
        # FIX DELAY: terima hasil nojoin() yang sudah dihitung di pemanggil
        # (start.py) supaya tidak perlu jalankan nojoin() lagi di sini —
        # sebelumnya dipanggil 2x per /start (sekali manual + sekali di
        # dalam usrikb), sekarang cukup sekali.
        nojoin = (
            await self.nojoin(user) if nojoin_list == '__unset__'
            else nojoin_list
        )
        if not self.fsubcids or not nojoin:
            return None
        buttons = []
        for cid in nojoin:
            if cid not in self.cacheids:
                continue
            title = self.cacheids[cid]['title']
            ilink = self.cacheids[cid]['ilink']
            if not ilink:  # FIX: skip jika invite link kosong/None
                continue
            buttons.append(pbtn('join', f'Join {title}', url=ilink, style='primary', fallback='☞'))
        layouts = [
            buttons[i: i + 2]
            for i in range(0, len(buttons), 2)
        ]
        if len(message.command) > 1:
            layouts.append(
                [
                    pbtn('tryagain', 'Try Again', url=self.urlstr(message.command[1]), fallback='🔄'),
                ],
            )
        if not layouts:  # FIX: jangan kirim ikb kosong → REPLY_MARKUP_INVALID
            return None
        return ckb(layouts)

    async def nojoin(self, user: int) -> list[int] or None:
        if not self.fsubcids or user in self.adminids:
            return None

        async def is_joined(cid: int) -> bool:
            try:
                await self._client_.get_chat_member(cid, user)
                return True
            except RPCError:
                return False

        # FIX DELAY: cek semua channel FSub secara PARALEL (asyncio.gather),
        # bukan satu-satu berurutan — kalau ada banyak channel FSub, ini
        # menghemat waktu signifikan dibanding await loop sequential lama.
        results = await asyncio.gather(*(is_joined(cid) for cid in self.fsubcids))
        return [
            cid for cid, joined in zip(self.fsubcids, results)
            if not joined
        ]

    def encode(self, first: int, last: int) -> str:
        _data = first * abs(self._client_.env.DATABASE_ID)
        data_ = last * abs(self._client_.env.DATABASE_ID)
        return self._client_.url.encode(f'id-{_data}-{data_}')

    def decode(self, string: str) -> list[int] | range:
        dbchid = self._client_.env.DATABASE_ID
        decoded = self._client_.url.decode(string).split('-')
        if len(decoded) == 2:
            return [int(int(decoded[1]) / abs(dbchid))]
        elif len(decoded) == 3:
            start = int(int(decoded[1]) / abs(dbchid))
            end = int(int(decoded[2]) / abs(dbchid))
            return (
                range(start, end + 1) if start < end
                else range(start, end - 1, -1)
            )

    async def getmsgs(self, ids: int):
        return await self._client_.get_messages(
            self._client_.env.DATABASE_ID,
            ids,
        )

    def build_caption(self, original_caption: str | None) -> str | None:
        """Terapkan caption kustom dari /setcaption HANYA kalau konten
        TIDAK punya caption/teks asli sendiri.

        - Konten sudah punya caption/teks (mis. video di-upload dengan
          caption manual oleh admin) -> caption asli dipakai apa adanya,
          /setcaption TIDAK ditambahkan/ditimpa sama sekali.
        - Konten media tanpa caption (gambar/video polos) -> caption dari
          /setcaption dipakai.
        - Belum ada /setcaption yang diset -> selalu kembalikan caption
          asli apa adanya (None tetap None)."""
        if original_caption:
            return original_caption
        return self.captiontext or original_caption

    def promo_markup(self) -> dict | None:
        """Tombol 🌟 PROMO VIP kalau link sudah di-set via /setpromo,
        atau None kalau belum (mirip get_promo_markup() di fsub2)."""
        if not self.promolink:
            return None
        return ckb([[btn('🌟 PROMO VIP 🌟', url=self.promolink, style='danger')]])

    def _today(self) -> str:
        import datetime
        return datetime.date.today().isoformat()

    async def quota_used_today(self, user: int) -> int:
        """Berapa kali user sudah pakai /view hari ini (mentah dari DB,
        TIDAK peduli admin/limit — dipakai buat tampilan 'sisa kuota')."""
        return await self._client_.mdb.get_quota(user, self._today())

    async def quota_remaining(self, user: int) -> bool:
        """Cek SAJA (tanpa memakai kuota) apakah member masih punya jatah
        /view hari ini. Dipakai SEBELUM daftar angka /view ditampilkan —
        supaya kalau kuota sudah habis, member langsung diarahkan ke
        notice VIP tanpa perlu lihat daftar dulu (persis alur bot asli
        Kingsuga: cek dulu sisa, baru scan channel kalau masih ada)."""
        if user in self.adminids or self.view_limit <= 0:
            return True
        used = await self.quota_used_today(user)
        return used < self.view_limit

    async def quota_ok(self, user: int) -> bool:
        """Cek + PAKAI 1 kuota /view harian member (VIEW_LIMIT, /setview
        limit). Dipakai pas video BENAR-BENAR dikirim (klik tombol angka),
        bukan pas daftar angka ditampilkan — pakai quota_remaining() untuk
        itu.

        - Admin & VIEW_LIMIT<=0 (unlimited) -> selalu True, tidak dihitung.
        - Selain itu -> True kalau counter hari ini MASIH di bawah limit
          (counter langsung dinaikkan 1), False kalau sudah kena limit
          (counter TIDAK dinaikkan lagi supaya tidak lanjut bertambah)."""
        if user in self.adminids or self.view_limit <= 0:
            return True
        today = self._today()
        used = await self._client_.mdb.get_quota(user, today)
        if used >= self.view_limit:
            return False
        await self._client_.mdb.bump_quota(user, today)
        return True

    def quota_notice_text(self) -> str:
        """Caption yang tampil saat member kehabisan kuota /view harian —
        dari /setquotatext kalau sudah diset, atau default ala Kingsuga.
        SELALU dipakai untuk member yang SUDAH join semua FSub tapi
        kuotanya habis -> diarahkan langsung order VIP (member yang
        BELUM join tetap kena JOIN_REQUIRED_TEXT dulu di plugins/view.py,
        bukan notice ini)."""
        if self.quota_text:
            return f'<b>{self.quota_text}</b>'
        return (
            '<blockquote><b>⛔ Kuota /view kamu hari ini sudah habis!\n\n'
            f'Batas harian: {self.view_limit}x\n\n'
            '💡 Ingin akses konten tanpa batas?\n'
            '👑 Upgrade ke VIP dan nikmati:\n'
            '✅ Akses konten lebih banyak\n'
            '✅ Update konten tiap hari\n'
            '✅ Video berkualitas\n\n'
            'Klik tombol di bawah untuk order VIP sekarang!</b></blockquote>'
        )

    def quota_notice_markup(self) -> dict | None:
        """Tombol 🌟 PROMO VIP yang ditempel di notice kuota habis —
        sama persis dengan promo_markup(), dipisah namanya biar jelas
        konteks pemakaiannya di pemanggil."""
        return self.promo_markup()

    def get_autodelete_delay(self) -> int | None:
        """Ambil durasi auto-delete (detik) hasil /autodelete.
        None       -> auto-delete dimatikan eksplisit lewat /autodelete off
        int        -> durasi aktif dalam detik
        (belum pernah diset -> dianggap mati, BEDA dari fsub2 yang defaultnya
        ON 30 menit, di sini default OFF supaya tidak mengubah perilaku lama
        untuk bot yang belum pernah pakai fitur ini)."""
        val = self.autodelete_raw
        if val is None:
            return None
        if str(val).lower() == 'off':
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    async def schedule_autodelete(self, chat_id: int, message_ids: list[int]) -> None:
        """Background task: tunggu durasi /autodelete lalu hapus pesan
        konten yang baru dikirim ke user, lalu kirim pesan pengganti berisi
        caption (/setcaption) + tombol 🌟 PROMO VIP (/setpromo) — mirip
        notice VIP di schedule_auto_delete() fsub2. Tidak melakukan apa-apa
        kalau fitur OFF."""
        delay = self.get_autodelete_delay()
        if delay is None or not message_ids:
            return
        await asyncio.sleep(delay)
        try:
            await self._client_.delete_messages(chat_id, message_ids)
        except RPCError:
            for mid in message_ids:
                with contextlib.suppress(RPCError):
                    await self._client_.delete_messages(chat_id, mid)

        # Kirim pesan pengganti: caption custom (kalau ada) + tombol promo.
        if self.captiontext:
            notice = f'<b>{self.captiontext}</b>'
        else:
            notice = (
                '⏳ <b>Konten otomatis dihapus.</b>\n\n'
                '🔓 Ingin akses tanpa batas waktu & tanpa expire?\n'
                '👇 Bergabung sebagai <b>Member VIP</b> sekarang!'
            )
        markup = self.promo_markup()
        with contextlib.suppress(Exception):
            await send_colored(
                self._client_,
                chat_id,
                notice,
                reply_markup=markup,
            )

    async def copymsgs(
        self,
        msg: Message,
        user: int,
    ) -> int | None:
        # PENTING: Pyrofork/Pyrogram .copy(caption=...) HANYA berlaku untuk
        # pesan media — untuk pesan teks murni parameter `caption` diabaikan
        # begitu saja (text aslinya yang dikirim apa adanya). Supaya
        # /setcaption juga menempel di konten teks, tangani dua kasus secara
        # eksplisit di sini.
        if msg.media:
            original_caption = msg.caption.html if msg.caption else None
            caption = self.build_caption(original_caption)
            sent = await msg.copy(
                user,
                caption=caption,
                protect_content=self.protectc,
            )
        else:
            original_text = msg.text.html if msg.text else ''
            text = self.build_caption(original_text) or original_text or '​'
            sent = await self._client_.send_message(
                user,
                text,
                disable_web_page_preview=True,
                protect_content=self.protectc,
            )
        # Pasang tombol 🌟 PROMO VIP berwarna via Bot API HTTP (sama seperti
        # copy_with_promo() di fsub2) — Pyrofork .copy(reply_markup=...)
        # tidak mendukung field `style` warna tombol.
        markup = self.promo_markup()
        if sent and markup:
            with contextlib.suppress(Exception):
                await edit_colored(self._client_, user, sent.id, reply_markup=markup)
        return sent.id if sent else None

    async def copymsg(self, msg: Message) -> int:
        copied = await msg.copy(
            self._client_.env.DATABASE_ID,
            disable_notification=True,
        )
        return copied.id

    def admikb(self) -> dict:
        buttons = []
        if self.fsubcids:
            for cid in self.fsubcids:
                if cid not in self.cacheids:
                    continue
                title = self.cacheids[cid]['title']
                ilink = self.cacheids[cid]['ilink']
                if not ilink:  # FIX: skip jika invite link kosong/None
                    continue
                buttons.append(pbtn('join', title, url=ilink, style='primary', fallback='🔔'))
        layouts = [
            buttons[i: i + 3]
            for i in range(0, len(buttons), 3)
        ]
        layouts.append(
            [
                pbtn('config', 'Configuration', data='home-home', style='danger', fallback='⚙️'),
            ],
        )
        return ckb(layouts)

    def joinkb(self, nojoin_list: list[int] | None = None) -> dict | None:
        """Tombol Join FSub polos (tanpa baris 'Try Again' seperti di
        usrikb()) — dipakai fitur /view & tombol 'Buka Media' saat user
        ternyata belum/sudah-tidak-lagi join semua channel/grup FSub.
        Beda dari usrikb(): tidak butuh objek Message (tidak ada payload
        /start yang perlu di-encode ulang di tombol 'Try Again').

        `nojoin_list` -> hasil helpers.nojoin(user) yang sudah dihitung di
        pemanggil. Kalau diisi, HANYA channel/grup yang belum di-join oleh
        user itu yang ditampilkan tombolnya (bukan semua FSub). Kalau
        None (tidak diisi), fallback ke perilaku lama: tampilkan semua
        FSub — supaya pemanggil lama yang belum di-update tetap jalan."""
        target_ids = nojoin_list if nojoin_list is not None else self.fsubcids
        if not target_ids:
            return None
        buttons = []
        for cid in target_ids:
            if cid not in self.cacheids:
                continue
            title = self.cacheids[cid]['title']
            ilink = self.cacheids[cid]['ilink']
            if not ilink:
                continue
            buttons.append(pbtn('join', f'Join {title}', url=ilink, style='primary', fallback='☞'))
        layouts = [
            buttons[i: i + 2]
            for i in range(0, len(buttons), 2)
        ]
        if not layouts:
            return None
        return ckb(layouts)

    def openviewkb(self, base: dict | None = None) -> dict:
        """Tombol '📂 Buka Media' yang ditempel di pesan start.

        SEKARANG tombol ini SELALU ditampilkan di pesan /start (tanpa
        payload) — baik saat user sudah join semua FSub maupun belum.
        - `base=None`            -> keyboard baru cuma berisi tombol ini
                                     (dipakai saat user sudah join, tidak
                                     ada tombol Join lain yang perlu
                                     ditampilkan).
        - `base=<keyboard join>` -> tombol ini ditempel sebagai baris
                                     TERAKHIR di bawah tombol-tombol Join
                                     yang sudah ada (dipakai saat user
                                     belum join).

        Klik tombolnya SELALU ditangani ulang oleh handler `^openview$`
        di plugins/view.py, yang mengecek status join user saat itu juga:
        - belum join  -> user diberi tahu "wajib join dulu" + tombol Join.
        - sudah join  -> daftar media langsung ditampilkan.
        Jadi aman ditampilkan ke siapa saja, termasuk yang belum join."""
        view_row = [
            pbtn('view', 'Buka Media', data='openview', style='primary', fallback='📁'),
        ]
        if not base or not base.get('inline_keyboard'):
            return ckb([view_row])
        rows = list(base['inline_keyboard'])
        rows.append(view_row)
        return ckb(rows)


helpers = Helpers(Bot)


class Decorator:
    @staticmethod
    def decorator(func) -> callable:
        @functools.wraps(func)
        async def wrapped(client, event):
            if hasattr(event, 'from_user'):
                user = event.from_user.id
            elif (
                hasattr(event, 'message')
                and hasattr(event.message, 'chat')
            ):
                user = event.message.chat.id
            else:
                return
            if user not in helpers.adminids:
                return
            await func(client, event)
        return wrapped

    def Admins(self, func) -> callable:
        return self.decorator(func)


decorator = Decorator()


class Markup:
    HOME = ckb([
        [
            btn('Generate Controller', 'set-gen', style='primary'),
        ],
        [
            btn('Start Text', 'set-strtmsg', style='success'),
            btn('Force Text', 'set-frcmsg', style='success'),
        ],
        [
            btn('Protect Content', 'set-prtctcntnt', style='primary'),
        ],
        [
            btn('Admin IDs', 'set-admnids', style='success'),
            btn('FSub IDs', 'set-fscids', style='primary'),
        ],
        [
            btn('Monitor and Stats', 'home-stats', style='success'),
        ],
        [
            btn('Close', 'home-close', style='danger'),
        ],
    ])

    STATS = ckb([
        [
            btn('Broadcast', 'stats-bc', style='primary'),
        ],
        [
            btn('Ping', 'stats-ping', style='success'),
            btn('Users', 'stats-users', style='primary'),
        ],
        [
            btn('« Back', 'home-home', style='success'),
        ],
    ])

    BACK = ckb([
        [
            btn('« Back', 'home-home', style='success'),
        ],
    ])

    SET_ADMIN = ckb([
        [
            btn('Add User', 'add-admnids', style='success'),
            btn('Del User', 'del-admnids', style='primary'),
        ],
        [
            btn('« Back', 'home-home', style='success'),
        ],
    ])

    SET_FSUB = ckb([
        [
            btn('Add Chat', 'add-fscids', style='success'),
            btn('Del Chat', 'del-fscids', style='primary'),
        ],
        [
            btn('« Back', 'home-home', style='success'),
        ],
    ])

    SET_PROTECT = ckb([
        [
            btn('« Back', 'home-home', style='success'),
            btn('Change', 'change-prtctcntnt', style='primary'),
        ],
    ])

    SET_GENERATOR = ckb([
        [
            btn('« Back', 'home-home', style='success'),
            btn('Change', 'change-gen', style='primary'),
        ],
    ])

    SET_START = ckb([
        [
            btn('« Back', 'home-home', style='success'),
            btn('Change', 'change-strtmsg', style='primary'),
        ],
    ])

    SET_FORCE = ckb([
        [
            btn('« Back', 'home-home', style='success'),
            btn('Change', 'change-frcmsg', style='primary'),
        ],
    ])

    BROADCAST_STATS = ckb([
        [
            btn('Stop', 'bc-abort', style='primary'),
            btn('Ref.', 'bc-refresh', style='success'),
        ],
    ])


CLOSE_ONLY = ckb([
    [
        btn('Close', 'home-close', style='danger'),
    ],
])


Markup = Markup()
