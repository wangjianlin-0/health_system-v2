import json

import pytest

from app.services import storage
from app.services.signals import decode


def legacy_schema(db):
    db.execute('CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT NOT NULL)')
    db.execute('CREATE TABLE records(id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), '
               'created_at TEXT, payload TEXT)')


def legacy_payload():
    return {
        'id': 'r1',
        'task_id': 't1',
        'created_at': '2026-10-01T00:00:00+00:00',
        'task_status': 'completed',
        'result': {
            'source': 'csv_import',
            'lead': 'lead_ii',
            'unit': 'mV',
            'sample_rate_hz': 250.0,
            'duration_sec': 0.012,
            'waveform': [0.1, 0.2, 0.3],
            'quality': {'status': 'basic_checks_passed', 'reasons': [], 'scope': 'test'},
            'prediction': {'status': 'model_unavailable', 'label': None, 'confidence': None,
                           'model_version': None, 'explanation': ''},
            'processing_version': 'p1',
        },
    }


def test_fresh_database_is_migrated_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', tmp_path / 'fresh.sqlite3')
    first = storage.initialize()
    assert first['current'] >= 5
    assert first['applied'] == [1, 2, 3, 4, 5]
    second = storage.initialize()
    assert second['applied'] == []
    assert second['current'] == first['current']
    with storage.connect() as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        tables = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        record_columns = {row['name'] for row in db.execute('PRAGMA table_info(records)')}
        task_columns = {row['name'] for row in db.execute('PRAGMA table_info(analysis_tasks)')}
    assert version == first['current']
    assert {'users', 'sessions', 'records', 'analysis_tasks', 'task_inputs',
            'task_events', 'record_signals', 'record_access_log', 'schema_migrations'} <= tables
    assert {'idx_records_owner_created', 'idx_tasks_owner_updated',
            'uq_tasks_idempotency'} <= indexes
    assert {'quality_status', 'heart_rate_bpm', 'n_samples', 'supersedes_record_id'} <= record_columns
    assert {'stage', 'heartbeat_at', 'cancel_requested', 'idempotency_key', 'input_path'} <= task_columns


def test_legacy_database_backfills_summary_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', tmp_path / 'legacy.sqlite3')
    with storage.connect() as db:
        legacy_schema(db)
        db.execute("INSERT INTO users VALUES ('u1','owner','hash')")
        db.execute("INSERT INTO records VALUES ('r1','u1','2026-10-01T00:00:00+00:00',?)",
                   (json.dumps(legacy_payload()),))
    info = storage.initialize()
    assert 1 in info['applied'] and 2 in info['applied']
    with storage.connect() as db:
        row = db.execute("SELECT * FROM records WHERE id='r1'").fetchone()
        signal = db.execute("SELECT * FROM record_signals WHERE record_id='r1'").fetchone()
    assert row['task_id'] == 't1'
    assert row['source'] == 'csv_import'
    assert row['lead'] == 'lead_ii'
    assert row['sample_rate_hz'] == 250.0
    assert row['n_samples'] == 3
    assert row['quality_status'] == 'basic_checks_passed'
    assert row['processing_version'] == 'p1'
    assert row['updated_at'] == row['created_at']
    payload = json.loads(row['payload'])
    assert 'waveform' not in payload['result']
    assert signal['encoding'] == 'f32le+zlib'
    assert decode(signal['data'], signal['encoding'], signal['n_samples']) == pytest.approx(
        [0.1, 0.2, 0.3], rel=1e-6)


def test_modified_migration_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', tmp_path / 'drift.sqlite3')
    storage.initialize()
    with storage.connect() as db:
        db.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
    with pytest.raises(RuntimeError, match='校验不一致'):
        storage.initialize()
