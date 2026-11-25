"""Optional profile fields for local accounts."""

VERSION = 7
NAME = "user_profile"


def apply(db):
    db.execute("ALTER TABLE users ADD COLUMN age INTEGER")
    db.execute("ALTER TABLE users ADD COLUMN sex TEXT")
