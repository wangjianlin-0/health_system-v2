import sqlite3
from datetime import datetime, timedelta, timezone

from app.services import records, storage
from app.services.backup import backup_database


def account(client, name):
    body = {'username': name, 'password': 'test-password-123'}
    assert client.post('/api/v1/auth/register', json=body).status_code == 200
    response = client.post('/api/v1/auth/login', json=body)
    return {'Authorization': 'Bearer ' + response.json()['token']}


def wait_task(client, headers, task_id, timeout=10):
    import time
    deadline = time.time() + timeout
    task = None
    while time.time() < deadline:
        task = client.get('/api/v1/tasks/' + task_id, headers=headers).json()
        if task['status'] in ('completed', 'failed', 'cancelled'):
            return task
        time.sleep(0.02)
    raise AssertionError(f'任务未结束：{task_id} {task}')


def upload_record(client, headers):
    response = client.post('/api/v1/analyze/ecg', headers=headers,
                           files={'file': ('signal.csv', 'value\n' + '0.1\n' * 600)},
                           data={'sample_rate_hz': '250'})
    assert response.status_code == 202
    return wait_task(client, headers, response.json()['id'])['record']


def test_task_events_include_and_permissions(client):
    owner, other = account(client, 'event-owner'), account(client, 'event-other')
    response = client.post('/api/v1/analyze/ecg', headers=owner,
                           files={'file': ('bad.csv', 'value\n0.1\n')},
                           data={'sample_rate_hz': '0'})
    assert response.status_code == 202
    task_id = response.json()['id']
    assert wait_task(client, owner, task_id)['status'] == 'failed'

    with_events = client.get(f'/api/v1/tasks/{task_id}?include_events=1', headers=owner)
    assert with_events.status_code == 200
    events = with_events.json()['events']
    assert [event['status'] for event in events] == ['pending', 'running', 'failed']
    assert events[-1]['error_code'] == 'input_invalid'
    assert all(event['created_at'] for event in events)

    without = client.get(f'/api/v1/tasks/{task_id}', headers=owner).json()
    assert 'events' not in without
    assert client.get(f'/api/v1/tasks/{task_id}?include_events=1', headers=other).status_code == 404


def test_access_log_query_filters_and_permissions(client):
    owner, relative = account(client, 'log-owner'), account(client, 'log-relative')
    record = upload_record(client, owner)
    path = f'/api/v1/records/{record["id"]}'
    client.get(path, headers=owner)
    client.get(f'{path}/export?format=csv', headers=owner)
    client.patch(path, json={'note': '审计测试'}, headers=owner)

    response = client.get(f'{path}/access-log?page=1&page_size=50', headers=owner)
    assert response.status_code == 200
    body = response.json()
    assert body['record_id'] == record['id']
    assert body['total'] >= 3
    actions = {item['action'] for item in body['items']}
    assert {'view', 'export', 'note'} <= actions
    assert all(item['actor_username'] == 'log-owner' for item in body['items'])

    filtered = client.get(f'{path}/access-log?action=export', headers=owner).json()
    assert filtered['items'] and all(item['action'] == 'export' for item in filtered['items'])
    assert client.get(f'{path}/access-log?action=bogus', headers=owner).status_code == 400

    grant = client.post('/api/v1/family/grants', json={'username': 'log-relative'},
                        headers=owner).json()
    assert client.get(f'{path}/access-log', headers=relative).status_code == 404
    client.delete('/api/v1/family/grants/' + grant['id'], headers=owner)


def test_audit_retention_purge(client):
    headers = account(client, 'retention-owner')
    record = upload_record(client, headers)
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    with storage.connect() as db:
        db.execute("INSERT INTO record_access_log(record_id, actor_id, action, detail, created_at) "
                   "VALUES (?,?,?,?,?)", (record['id'], 'old-actor', 'view', None, old))
    removed = records.purge_audit_log(90)
    assert removed == 1
    with storage.connect() as db:
        remaining = db.execute("SELECT COUNT(*) FROM record_access_log WHERE record_id=?",
                               (record['id'],)).fetchone()[0]
    assert remaining >= 1
    assert records.purge_audit_log(0) == 0


def test_backup_database_and_retention(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', tmp_path / 'backup.sqlite3')
    storage.initialize()
    with storage.connect() as db:
        db.execute("INSERT INTO users(id, username, password_hash) VALUES ('u-backup','backup','x') "
                   "ON CONFLICT(id) DO NOTHING")
        db.execute("INSERT INTO records(id, owner_id, created_at, payload) "
                   "VALUES ('r-backup','u-backup',?, '{}') ON CONFLICT(id) DO NOTHING",
                   (datetime.now(timezone.utc).isoformat(),))
    target = tmp_path / 'backups'
    first = backup_database(target, keep=2)
    second = backup_database(target, keep=2)
    third = backup_database(target, keep=2)
    assert first['integrity'] == 'ok'
    assert first['records'] >= 1
    assert third['removed']
    copies = sorted(target.glob('health-*.sqlite3'))
    assert len(copies) == 2
    check = sqlite3.connect(copies[-1])
    try:
        assert check.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert check.execute('SELECT COUNT(*) FROM records').fetchone()[0] >= 1
    finally:
        check.close()
