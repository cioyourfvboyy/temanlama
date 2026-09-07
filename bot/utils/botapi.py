"""
bot/utils/botapi.py
====================
Klien HTTP tipis ke Telegram Bot API (https://api.telegram.org/bot<token>/...).

KENAPA INI ADA
--------------
Bot ini berjalan di atas Pyrofork (MTProto), bukan Bot API HTTP biasa.
Fitur "colored button" (field `style` pada InlineKeyboardButton: primary /
success / danger) baru ditambahkan Telegram di Bot API 9.4 (9 Feb 2026)
dan BELUM ada di skema MTProto / Pyrofork manapun — lihat:
https://core.telegram.org/bots/api-changelog#february-9-2026

Karena itu, untuk tombol berwarna, kita memanggil Bot API HTTP secara
langsung lewat modul ini, di samping Pyrofork yang tetap menjadi mesin
utama bot (listen, callback_query, semua logic lain TIDAK berubah).

ATURAN KERAS — JANGAN DILANGGAR
--------------------------------
Modul ini TIDAK BOLEH memanggil `getUpdates` atau `setWebhook`.
Telegram hanya mengizinkan SATU consumer update (poller) aktif per bot
token. Pyrofork sudah menjadi poller itu (lewat MTProto). Kalau modul ini
ikut polling, akan terjadi 409 Conflict dan Pyrofork bisa berhenti
menerima update. Modul ini HANYA boleh melakukan panggilan "fire" satu
arah: sendMessage, editMessageText, editMessageReplyMarkup, answerCallbackQuery,
dan sejenisnya — semuanya method yang TIDAK membaca antrian update.

Karena bot token yang sama dipakai di kedua sisi (MTProto & HTTP), pesan
yang dikirim lewat salah satu jalur tetap bisa diedit/dibalas lewat jalur
lainnya — message_id & chat_id konsisten di kedua API.
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from .logger import Logger

_FORBIDDEN_METHODS = {'getupdates', 'setwebhook'}


class BotAPIError(Exception):
    """Dilempar saat Telegram Bot API mengembalikan ok=False."""

    def __init__(self, method: str, description: str, error_code: int | None = None):
        self.method = method
        self.description = description
        self.error_code = error_code
        super().__init__(f'{method} failed ({error_code}): {description}')


class BotAPI:
    """
    Klien Bot API HTTP dengan session persisten (di-reuse antar panggilan),
    BUKAN sekali-pakai.

    FIX (delay): sebelumnya tiap pemanggilan `BotAPI(token)` lewat
    `async with` membuat `aiohttp.ClientSession` baru lalu langsung
    menutupnya setelah satu request — artinya tiap tombol/start/edit
    selalu bikin koneksi TCP+TLS baru ke api.telegram.org dari nol.
    Itu sumber delay yang terasa di /start dan semua tombol berwarna.
    Sekarang session dibuat sekali (class-level, shared) dan dipakai
    ulang terus lewat connector pooling aiohttp, persis seperti pola
    fix non-persistent aiohttp session yang sudah dipakai di fsub2.

    Penggunaan (tetap sama persis di pemanggil, tidak ada breaking change):
        async with BotAPI(bot_token) as api:
            await api.call(...)
    `__aexit__` di sini SENGAJA tidak menutup session (lihat di bawah).
    """

    BASE_URL = 'https://api.telegram.org/bot{token}/{method}'

    # Session di-share di level class, per token, supaya semua instance
    # BotAPI(token) yang dibuat di banyak tempat (configs.py, start.py, dst)
    # tetap pakai satu koneksi pool yang sama, bukan bikin baru tiap call.
    _sessions: dict[str, aiohttp.ClientSession] = {}

    def __init__(self, token: str):
        if not token:
            raise ValueError('Bot token kosong — BotAPI tidak bisa diinisialisasi.')
        self._token = token

    async def _get_session(self) -> aiohttp.ClientSession:
        session = BotAPI._sessions.get(self._token)
        if session is None or session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(limit=20, keepalive_timeout=60)
            session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            BotAPI._sessions[self._token] = session
        return session

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """
        Panggil satu method Bot API. Mengembalikan field `result` jika
        ok=True. Melempar BotAPIError jika ok=False.
        """
        if method.lower() in _FORBIDDEN_METHODS:
            # Pagar pengaman keras: modul ini tidak boleh dipakai untuk
            # menerima update, hanya untuk mengirim/mengubah pesan.
            raise RuntimeError(
                f"BotAPI.call('{method}') ditolak: modul ini hanya untuk "
                'panggilan satu-arah (send/edit), bukan untuk menerima update. '
                'Pyrofork tetap satu-satunya poller getUpdates untuk bot ini.',
            )

        url = self.BASE_URL.format(token=self._token, method=method)
        session = await self._get_session()
        payload = _clean(params or {})

        try:
            async with session.post(
                url,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
            ) as resp:
                data = await resp.json()
        except aiohttp.ClientError as e:
            Logger.warning(f'BotAPI[{method}] network error: {e}')
            raise

        if not data.get('ok'):
            Logger.warning(
                f"BotAPI[{method}] error {data.get('error_code')}: "
                f"{data.get('description')}",
            )
            raise BotAPIError(
                method,
                data.get('description', 'unknown error'),
                data.get('error_code'),
            )
        return data.get('result')

    async def close(self):
        """Tutup session yang di-share untuk token ini. Hanya dipanggil saat
        bot benar-benar shutdown (mis. di Bot.stop()), BUKAN tiap selesai
        satu request — itulah yang dulu bikin delay."""
        session = BotAPI._sessions.pop(self._token, None)
        if session and not session.closed:
            await session.close()

    async def __aenter__(self) -> 'BotAPI':
        return self

    async def __aexit__(self, *exc):
        # SENGAJA tidak menutup session di sini. Session di-share dan harus
        # tetap hidup supaya request berikutnya bisa reuse koneksi yang sama
        # (keep-alive), bukan bikin handshake TCP/TLS baru tiap kali.
        pass


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Buang key dengan value None agar tidak ikut terserialisasi."""
    return {k: v for k, v in d.items() if v is not None}
