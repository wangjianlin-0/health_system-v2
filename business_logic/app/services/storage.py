"""王书阁：连接、迁移与记录存储；业务模块负责各自表的数据操作。"""
import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path

DB = Path(os.environ.get('HEALTH_DB_PATH', str(Path(__file__).resolve().parents[3] / 'runtime' / 'health.sqlite3')))

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()

def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL);
        CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), created_at TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS grants(
            id TEXT PRIMARY KEY,
            owner_id TEXT REFERENCES users(id),
            relative_id TEXT REFERENCES users(id),
            active INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            permissions TEXT NOT NULL DEFAULT 'records:list,records:read',
            created_at REAL,
            responded_at REAL
        );
        CREATE TABLE IF NOT EXISTS notifications(
            id TEXT PRIMARY KEY,
            recipient_id TEXT REFERENCES users(id),
            grant_id TEXT REFERENCES grants(id),
            message TEXT,
            status TEXT,
            kind TEXT NOT NULL DEFAULT 'grant_update',
            created_at REAL,
            read_at REAL
        );
        ''')

        # SQLite 的 CREATE TABLE IF NOT EXISTS 不会为旧表补列。这里采用可重复执行的
        # 小型迁移，让已有开发数据库可以继续使用，而不要求删除 runtime 数据。
        grant_columns = {row['name'] for row in db.execute('PRAGMA table_info(grants)')}
        status_was_missing = 'status' not in grant_columns
        for name, definition in {
            'status': "TEXT NOT NULL DEFAULT 'pending'",
            'permissions': "TEXT NOT NULL DEFAULT 'records:list,records:read'",
            'created_at': 'REAL',
            'responded_at': 'REAL',
        }.items():
            if name not in grant_columns:
                db.execute(f'ALTER TABLE grants ADD COLUMN {name} {definition}')

        notification_columns = {row['name'] for row in db.execute('PRAGMA table_info(notifications)')}
        for name, definition in {
            'kind': "TEXT NOT NULL DEFAULT 'grant_update'",
            'created_at': 'REAL',
            'read_at': 'REAL',
        }.items():
            if name not in notification_columns:
                db.execute(f'ALTER TABLE notifications ADD COLUMN {name} {definition}')

        # 旧版 active=1 代表已直接授权；迁移后将其视为 accepted。
        if status_was_missing:
            db.execute("UPDATE grants SET status=CASE WHEN active=1 THEN 'accepted' ELSE 'revoked' END")
        else:
            db.execute("UPDATE grants SET status=CASE WHEN active=1 THEN 'accepted' ELSE 'revoked' END WHERE status IS NULL OR status=''")
        db.execute("UPDATE grants SET permissions='records:list,records:read' WHERE permissions IS NULL OR permissions=''")
        db.execute("UPDATE notifications SET status='unread' WHERE status='in_app_available' OR status IS NULL OR status=''")
