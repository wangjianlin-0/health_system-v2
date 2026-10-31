"""迁移执行器：版本表 + 校验和 + 单事务应用。"""
from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / 'db' / 'migrations'


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
    applied = {row['version']: row for row in db.execute('SELECT version, checksum FROM schema_migrations')}
    current = max(applied, default=0)
    applied_now = []
    for path in sorted(directory.glob('[0-9]*.py')):
        module = _load(path)
        version = int(getattr(module, 'VERSION', -1))
        name = str(getattr(module, 'NAME', path.stem))
        if version <= 0 or not callable(getattr(module, 'apply', None)):
            raise RuntimeError(f'迁移文件格式不正确：{path.name}')
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if version in applied:
            if applied[version]['checksum'] != checksum:
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
