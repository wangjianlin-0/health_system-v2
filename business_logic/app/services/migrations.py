"""迁移执行器：版本表 + 校验和 + 单事务应用。"""
from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'db' / 'migrations'
MAIN_FAMILY_CARE_V7 = {
    '14a2c98a904ba24e229b92337f0504e6a1476a9202a641df2fdffc14fb8cb9a4',
    'f0c35cbd2659e5a853b797ba1f0933569c13b5309b2fb80d1c60a7e19e4ac78c',
}
FAMILY_CARE_V9 = '596207546688b0a7d05e9edd9fb7a50c51315402b98fd6f379a175b9e5830aad'


def _align_family_care_version(db, directory: Path) -> None:
    """Map the original main migration to its identical schema at version 9."""
    target = directory / '0009_family_care.py'
    if not target.is_file():
        return
    row = db.execute('SELECT name, checksum FROM schema_migrations WHERE version = 7').fetchone()
    if not row or row['name'] != 'family_care' or row['checksum'] not in MAIN_FAMILY_CARE_V7:
        return
    if hashlib.sha256(target.read_bytes()).hexdigest() != FAMILY_CARE_V9:
        raise RuntimeError('迁移 0009_family_care.py 校验不一致')
    db.execute('UPDATE schema_migrations SET version = 9, checksum = ? WHERE version = 7',
               (FAMILY_CARE_V9,))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f'ecg_migration_{path.stem}', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'无法加载迁移文件：{path.name}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations(db, directory: Path | None = None) -> dict:
    """按版本顺序应用未执行的迁移，返回当前版本与本次新增版本。"""
    directory = directory or MIGRATIONS_DIR
    db.execute('''CREATE TABLE IF NOT EXISTS schema_migrations(
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL)''')
    _align_family_care_version(db, directory)
    applied = {row['version']: row for row in db.execute('SELECT version, checksum FROM schema_migrations')}
    current = max(applied, default=0)
    applied_now = []
    for path in sorted(directory.glob('[0-9]*.py')):
        module = _load(path)
        version = int(getattr(module, 'VERSION', -1))
        name = str(getattr(module, 'NAME', path.stem))
        if version <= 0 or not callable(getattr(module, 'apply', None)):
            raise RuntimeError(f'迁移文件格式不正确：{path.name}')
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        if version in applied:
            # Older Windows checkouts could apply the same migration as CRLF.
            lf = content.replace(b'\r\n', b'\n')
            compatible_checksums = {checksum, hashlib.sha256(lf).hexdigest(),
                                    hashlib.sha256(lf.replace(b'\n', b'\r\n')).hexdigest()}
            if applied[version]['checksum'] not in compatible_checksums:
                raise RuntimeError(f'迁移 {path.name} 校验不一致；已应用的迁移不允许修改')
            continue
        module.apply(db)
        db.execute(
            'INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (?,?,?,?)',
            (version, name, checksum, datetime.now(timezone.utc).isoformat()),
        )
        applied_now.append(version)
        current = max(current, version)
    db.execute(f'PRAGMA user_version = {current}')
    return {'current': current, 'applied': applied_now}
