"""Require recipient confirmation for new family grants; retain existing grants."""
VERSION = 6
NAME = 'family_invitations'


def apply(db):
    db.execute("ALTER TABLE grants ADD COLUMN status TEXT NOT NULL DEFAULT 'accepted'")
    db.execute("ALTER TABLE grants ADD COLUMN created_at REAL NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE grants ADD COLUMN expires_at REAL")
    db.execute("UPDATE grants SET status='revoked' WHERE active=0")
    db.execute('CREATE INDEX idx_grants_status_expiry ON grants(status,expires_at)')
