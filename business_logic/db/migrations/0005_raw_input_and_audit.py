"""原始输入路径与访问审计。"""

VERSION = 5
NAME = 'raw_input_and_audit'


def apply(db):
    columns = {row['name'] for row in db.execute('PRAGMA table_info(analysis_tasks)')}
    if 'input_path' not in columns:
        db.execute('ALTER TABLE analysis_tasks ADD COLUMN input_path TEXT')
    db.execute('''CREATE TABLE IF NOT EXISTS record_access_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id TEXT,
        actor_id TEXT,
        action TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_access_record ON record_access_log(record_id, id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_access_actor ON record_access_log(actor_id, id)')
