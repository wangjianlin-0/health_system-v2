"""记录模块：连接参数、PRAGMA 与迁移入口；业务模块负责各自表的数据操作。"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings

DB = Path(os.environ.get('HEALTH_DB_PATH') or settings.db_path)


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA synchronous=NORMAL')
    connection.execute('PRAGMA busy_timeout=5000')
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA temp_store=MEMORY')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize() -> dict:
    """建库或升级到最新 schema；旧代码直接调用 initialize() 仍然可用。"""
    from app.services.migrations import run_migrations

    with connect() as db:
        return run_migrations(db)


def reset_for_tests(path: Path) -> None:
    global DB
    DB = path
