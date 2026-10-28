import time
from pathlib import Path

from app.services import storage


def account(client, name):
    body = {'username': name, 'password': 'test-password-123'}
    assert client.post('/api/v1/auth/register', json=body).status_code == 200
    response = client.post('/api/v1/auth/login', json=body)
    return {'Authorization': 'Bearer ' + response.json()['token']}


def wait_task(client, headers, task_id, timeout=10):
    deadline = time.time() + timeout
    task = None
    while time.time() < deadline:
        task = client.get('/api/v1/tasks/' + task_id, headers=headers).json()
        if task['status'] in ('completed', 'failed', 'cancelled'):
            return task
        time.sleep(0.02)
    raise AssertionError(f'任务未结束：{task_id} {task}')


def replay_record(client, headers):
    response = client.post('/api/v1/acquisition/replay', headers=headers)
    assert response.status_code == 202
    return wait_task(client, headers, response.json()['id'])['record']


def upload_record(client, headers, content='value\n' + '0.1\n' * 600):
    response = client.post('/api/v1/analyze/ecg', headers=headers,
                           files={'file': ('signal.csv', content)},
                           data={'sample_rate_hz': '250'})
    assert response.status_code == 202
    return wait_task(client, headers, response.json()['id'])['record'], content.encode()


def test_waveform_window_and_shared_permission(client):
    owner, relative = account(client, 'wave-owner'), account(client, 'wave-relative')
    record = replay_record(client, owner)
    path = f'/api/v1/records/{record["id"]}/waveform'
    full = client.get(path + '?max_points=120&mode=envelope', headers=owner)
    assert full.status_code == 200
    body = full.json()
    assert body['total_samples'] == 2500
    assert body['returned_points'] == len(body['points'])
    assert body['returned_points'] <= 240
    assert body['points'][0]['t'] == 0.0
    assert body['unit'] == 'mV' and body['sample_rate_hz'] == 250.0

    window = client.get(path + '?start_sec=1&end_sec=2&max_points=100&mode=mean', headers=owner)
    assert window.status_code == 200
    points = window.json()['points']
    assert points and all(1.0 <= point['t'] <= 2.0 for point in points)
    assert window.json()['start_sec'] == 1.0

    assert client.get(path + '?start_sec=2&end_sec=1', headers=owner).status_code == 400
    assert client.get(path + '?mode=bad', headers=owner).status_code == 422
    assert client.get(path, headers=relative).status_code == 404
    grant = client.post('/api/v1/family/grants', json={'username': 'wave-relative'},
                        headers=owner).json()
    assert client.get(path + '?max_points=100', headers=relative).status_code == 200
    client.delete('/api/v1/family/grants/' + grant['id'], headers=owner)
    assert client.get(path, headers=relative).status_code == 404


def test_raw_upload_download_and_export(client):
    owner, other = account(client, 'raw-owner'), account(client, 'raw-other')
    record, content = upload_record(client, owner)
    detail = client.get('/api/v1/records/' + record['id'], headers=owner).json()
    assert detail['has_raw_file'] is True
    assert detail['owned'] is True

    raw = client.get(f'/api/v1/records/{record["id"]}/raw', headers=owner)
    assert raw.status_code == 200
    assert raw.content == content
    assert 'attachment' in raw.headers['content-disposition']
    exported = client.get(f'/api/v1/records/{record["id"]}/export?format=raw', headers=owner)
    assert exported.status_code == 200
    assert exported.content == content
    assert client.get(f'/api/v1/records/{record["id"]}/raw', headers=other).status_code == 404

    replay = replay_record(client, owner)
    missing = client.get(f'/api/v1/records/{replay["id"]}/raw', headers=owner)
    assert missing.status_code == 409
    assert missing.json()['code'] == 'input_unavailable'


def test_reanalyze_creates_new_record_and_keeps_old(client):
    owner, relative = account(client, 're-owner'), account(client, 're-relative')
    original, _ = upload_record(client, owner)
    response = client.post(f'/api/v1/records/{original["id"]}/reanalyze', headers=owner)
    assert response.status_code == 202
    new_task = response.json()
    assert new_task['status'] == 'pending'
    new_record = wait_task(client, owner, new_task['id'])['record']
    assert new_record['id'] != original['id']
    assert new_record['supersedes_record_id'] == original['id']
    assert new_record['task_id'] == new_task['id']
    assert new_record['n_samples'] == original['n_samples']
    assert new_record['has_raw_file'] is True
    assert client.get('/api/v1/records/' + original['id'], headers=owner).status_code == 200
    assert client.get('/api/v1/tasks?page=1&page_size=10', headers=owner).json()['total'] == 2

    grant = client.post('/api/v1/family/grants', json={'username': 're-relative'},
                        headers=owner).json()
    assert client.post(f'/api/v1/records/{original["id"]}/reanalyze',
                       headers=relative).status_code == 404
    client.delete('/api/v1/family/grants/' + grant['id'], headers=owner)

    assert client.delete('/api/v1/records/' + original['id'], headers=owner).status_code == 200
    survivor = client.get('/api/v1/records/' + new_record['id'], headers=owner)
    assert survivor.status_code == 200
    assert survivor.json()['supersedes_record_id'] is None
    assert survivor.json()['has_raw_file'] is True


def test_note_patch_permissions_and_export(client):
    owner, relative = account(client, 'note-owner'), account(client, 'note-relative')
    record = replay_record(client, owner)
    updated = client.patch(f'/api/v1/records/{record["id"]}',
                           json={'note': '早上起床后测量，服药前'}, headers=owner)
    assert updated.status_code == 200
    assert updated.json()['note'] == '早上起床后测量，服药前'
    assert client.get('/api/v1/records/' + record['id'], headers=owner).json()['note'] == '早上起床后测量，服药前'
    exported = client.get(f'/api/v1/records/{record["id"]}/export?format=json', headers=owner).json()
    assert exported['note'] == '早上起床后测量，服药前'
    assert client.patch(f'/api/v1/records/{record["id"]}',
                        json={'note': 'x' * 501}, headers=owner).status_code == 422
    assert client.patch(f'/api/v1/records/{record["id"]}',
                        json={'note': 'ok', 'extra': 1}, headers=owner).status_code == 422

    grant = client.post('/api/v1/family/grants', json={'username': 'note-relative'},
                        headers=owner).json()
    assert client.patch(f'/api/v1/records/{record["id"]}',
                        json={'note': 'nope'}, headers=relative).status_code == 404
    client.delete('/api/v1/family/grants/' + grant['id'], headers=owner)


def test_audit_log_and_delete_cascade(client):
    headers = account(client, 'audit-owner')
    record, _ = upload_record(client, headers)
    client.get('/api/v1/records/' + record['id'], headers=headers)
    client.get(f'/api/v1/records/{record["id"]}/export?format=csv', headers=headers)
    with storage.connect() as db:
        actions = [row['action'] for row in db.execute(
            'SELECT action FROM record_access_log WHERE record_id=? ORDER BY id', (record['id'],))]
        raw_path = db.execute('SELECT input_path FROM records WHERE id=?', (record['id'],)).fetchone()[0]
        assert db.execute('SELECT COUNT(*) FROM record_signals WHERE record_id=?',
                          (record['id'],)).fetchone()[0] == 1
    assert {'view', 'export'} <= set(actions)
    assert raw_path and Path(raw_path).is_file()

    assert client.delete('/api/v1/records/' + record['id'], headers=headers).status_code == 200
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM record_signals WHERE record_id=?',
                          (record['id'],)).fetchone()[0] == 0
        actions = [row['action'] for row in db.execute(
            'SELECT action FROM record_access_log WHERE record_id=? ORDER BY id', (record['id'],))]
    assert 'delete' in actions
    assert not Path(raw_path).exists()
