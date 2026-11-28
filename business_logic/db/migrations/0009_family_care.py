"""Persist collaboration data within a single accepted sharing relationship."""

VERSION = 9
NAME = 'family_care'


def apply(db):
    db.execute("""CREATE TABLE family_care_items (
        id TEXT PRIMARY KEY, grant_id TEXT NOT NULL REFERENCES grants(id),
        title TEXT NOT NULL, due_date TEXT NOT NULL, due_time TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)))""")
    db.execute("""CREATE TABLE family_care_messages (
        id TEXT PRIMARY KEY, grant_id TEXT NOT NULL REFERENCES grants(id),
        sender_id TEXT NOT NULL REFERENCES users(id), text TEXT NOT NULL,
        created_at TEXT NOT NULL, read_at TEXT)""")
    db.execute("""CREATE TABLE family_care_contacts (
        id TEXT PRIMARY KEY, grant_id TEXT NOT NULL REFERENCES grants(id),
        name TEXT NOT NULL, relation TEXT NOT NULL, phone TEXT NOT NULL,
        preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)))""")
    db.execute("""CREATE TABLE family_care_settings (
        grant_id TEXT PRIMARY KEY REFERENCES grants(id), callback_phone TEXT NOT NULL)""")
    db.execute("""CREATE TABLE family_care_drills (
        id TEXT PRIMARY KEY, grant_id TEXT NOT NULL REFERENCES grants(id),
        sender_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        acknowledged_at TEXT)""")
    db.execute('CREATE INDEX idx_care_items_grant_day ON family_care_items(grant_id,due_date,due_time)')
    db.execute('CREATE INDEX idx_care_messages_grant_time ON family_care_messages(grant_id,created_at)')
    db.execute('CREATE INDEX idx_care_drills_grant_time ON family_care_drills(grant_id,created_at)')
    db.execute('CREATE UNIQUE INDEX uq_care_preferred_contact ON family_care_contacts(grant_id) WHERE preferred=1')
