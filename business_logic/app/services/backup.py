"""SQLite 一致性备份：使用 sqlite3 backup API，并校验备份可读。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.services import storage


def backup_database(target_dir: str | Path | None = None, keep: int = 10) -> dict:
    source_path = Path(storage.DB)
    if not source_path.is_file():
        raise FileNotFoundError(f'数据库不存在：{source_path}')
    target = Path(target_dir) if target_dir else source_path.parent / 'backups'
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination = target / f'health-{stamp}.sqlite3'

    source = sqlite3.connect(source_path)
    try:
        copy = sqlite3.connect(destination)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()

    check = sqlite3.connect(destination)
    try:
        integrity = check.execute('PRAGMA integrity_check').fetchone()[0]
        records = check.execute('SELECT COUNT(*) FROM records').fetchone()[0]
    finally:
        check.close()
    if integrity != 'ok':
        destination.unlink(missing_ok=True)
        raise RuntimeError(f'备份校验失败：{integrity}')

    removed = []
    if keep > 0:
        files = sorted(target.glob('health-*.sqlite3'))
        for old in files[:-keep]:
            old.unlink(missing_ok=True)
            removed.append(old.name)

    return {
        'path': str(destination),
        'bytes': destination.stat().st_size,
        'records': records,
        'integrity': integrity,
        'removed': removed,
    }
