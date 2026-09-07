"""
Backup & Restore utilitas untuk SQLite database.

Fungsi:
  create_backup_zip()  → bytes  (zip berisi bot.db)
  restore_from_zip(data: bytes)  → None
  send_db_backup(client, chat_id, caption)  → kirim zip ke Telegram
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime

from config import Config


def create_backup_zip() -> bytes:
    """Buat zip berisi file SQLite DB, kembalikan sebagai bytes."""
    db_path = Config.DB_PATH
    if not os.path.exists(db_path):
        raise FileNotFoundError(f'DB tidak ditemukan: {db_path}')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, arcname=os.path.basename(db_path))
    buf.seek(0)
    return buf.read()


def restore_from_zip(data: bytes) -> None:
    """Ekstrak file DB dari zip bytes dan timpa DB aktif."""
    db_path = Config.DB_PATH
    db_dir  = os.path.dirname(db_path) or '.'
    os.makedirs(db_dir, exist_ok=True)

    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, 'r') as zf:
        names = zf.namelist()
        # Cari file .db di dalam zip
        db_files = [n for n in names if n.endswith('.db')]
        if not db_files:
            raise ValueError('Tidak ada file .db di dalam zip.')
        # Ekstrak langsung ke path DB
        with zf.open(db_files[0]) as src, open(db_path, 'wb') as dst:
            dst.write(src.read())


async def send_db_backup(client, chat_id: int, caption: str = '') -> None:
    """Kirim file zip backup DB ke chat_id via Telegram."""
    if not chat_id:
        return
    try:
        zip_bytes = create_backup_zip()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'db_backup_{ts}.zip'

        buf = io.BytesIO(zip_bytes)
        buf.name = filename

        cap = caption or f'📦 **DB Backup**\n`{filename}`'
        await client.send_document(
            chat_id,
            buf,
            caption=cap,
            file_name=filename,
        )
    except Exception as e:
        client.log.warning(f'[Backup] Gagal kirim backup: {e}')
