"""基线 schema：与旧 initialize() 等价，仅用 IF NOT EXISTS 保证既有库可继续。"""

VERSION = 1
NAME = 'baseline'


def apply(db):
    db.execute('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), created_at TEXT, payload TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS analysis_tasks(
        id TEXT PRIMARY KEY,
        owner_id TEXT REFERENCES users(id),
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        error TEXT,
        record_id TEXT REFERENCES records(id),
        processing_version TEXT NOT NULL)''')
    db.execute('CREATE TABLE IF NOT EXISTS task_inputs(task_id TEXT PRIMARY KEY REFERENCES analysis_tasks(id), payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), relative_id TEXT REFERENCES users(id), active INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY, recipient_id TEXT REFERENCES users(id), grant_id TEXT REFERENCES grants(id), message TEXT, status TEXT)')
