"""任务运行字段、事件表与幂等索引。"""

VERSION = 3
NAME = 'task_runtime'

COLUMNS = [
    ('stage', 'TEXT'),
    ('source', 'TEXT'),
    ('outcome', 'TEXT'),
    ('error_code', 'TEXT'),
    ('worker_id', 'TEXT'),
    ('started_at', 'TEXT'),
    ('finished_at', 'TEXT'),
    ('heartbeat_at', 'TEXT'),
    ('cancel_requested', 'INTEGER NOT NULL DEFAULT 0'),
    ('attempt', 'INTEGER NOT NULL DEFAULT 0'),
    ('input_sha256', 'TEXT'),
    ('idempotency_key', 'TEXT'),
    ('source_record_id', 'TEXT REFERENCES records(id)'),
]


def apply(db):
    existing = {row['name'] for row in db.execute('PRAGMA table_info(analysis_tasks)')}
    for name, kind in COLUMNS:
        if name not in existing:
            db.execute(f'ALTER TABLE analysis_tasks ADD COLUMN {name} {kind}')
    db.execute('''UPDATE analysis_tasks SET source = (
        SELECT json_extract(i.payload, '$.source') FROM task_inputs i WHERE i.task_id = analysis_tasks.id
    ) WHERE source IS NULL''')
    db.execute('''CREATE TABLE IF NOT EXISTS task_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL REFERENCES analysis_tasks(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        stage TEXT,
        error_code TEXT,
        detail TEXT,
        created_at TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_tasks_owner_updated ON analysis_tasks(owner_id, updated_at DESC)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON analysis_tasks(status, created_at)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_idempotency ON analysis_tasks(owner_id, idempotency_key) WHERE idempotency_key IS NOT NULL')
    db.execute('CREATE INDEX IF NOT EXISTS idx_grants_relative_active ON grants(relative_id, active, owner_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id)')
