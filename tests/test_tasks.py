import time

import pytest

from app.core.runner import runner
from app.services import records, storage


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


def replay(client, headers):
    response = client.post('/api/v1/acquisition/replay', headers=headers)
    assert response.status_code == 202
    return response.json()['id']


def upload(client, headers, key=None, content='value\n' + '0.1\n' * 600):
    extra = {'Idempotency-Key': key} if key else {}
    return client.post('/api/v1/analyze/ecg', headers={**headers, **extra},
                       files={'file': ('signal.csv', content)}, data={'sample_rate_hz': '250'})


def test_task_list_owner_only_and_filters(client, monkeypatch):
    monkeypatch.setattr(runner, 'enqueue', lambda task_id: None)
    headers = account(client, 'task-list')
    ids = {replay(client, headers), replay(client, headers)}
    page = client.get('/api/v1/tasks?page=1&page_size=10', headers=headers).json()
    assert page['total'] == 2
    assert {item['id'] for item in page['items']} == ids
    assert page['items'][0]['stage'] == 'queued'
    pending = client.get('/api/v1/tasks?status=pending', headers=headers).json()
    assert pending['total'] == 2
    assert client.get('/api/v1/tasks?status=running', headers=headers).json()['total'] == 0
    assert client.get('/api/v1/tasks?status=bogus', headers=headers).status_code == 400
    other = account(client, 'task-list-other')
    assert client.get('/api/v1/tasks', headers=other).json()['total'] == 0
    assert client.get('/api/v1/tasks/' + next(iter(ids)), headers=other).status_code == 404


def test_cancel_pending_and_terminal(client, monkeypatch):
    monkeypatch.setattr(runner, 'enqueue', lambda task_id: None)
    headers = account(client, 'task-cancel')
    task_id = replay(client, headers)
    cancelled = client.post(f'/api/v1/tasks/{task_id}/cancel', headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()['status'] == 'cancelled'
    assert cancelled.json()['error_code'] == 'cancelled'
    again = client.post(f'/api/v1/tasks/{task_id}/cancel', headers=headers)
    assert again.status_code == 409
    assert again.json()['code'] == 'task_finished'
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM records').fetchone()[0] == 0
        assert db.execute("SELECT status FROM task_events WHERE task_id=? AND status='cancelled'",
                          (task_id,)).fetchone() is not None


def test_cancel_running_then_worker_finalizes(client, monkeypatch):
    monkeypatch.setattr(runner, 'enqueue', lambda task_id: None)
    headers = account(client, 'task-running')
    task_id = replay(client, headers)
    with storage.connect() as db:
        db.execute("UPDATE analysis_tasks SET status='running' WHERE id=?", (task_id,))
    response = client.post(f'/api/v1/tasks/{task_id}/cancel', headers=headers)
    assert response.status_code == 200
    assert response.json()['status'] == 'running'
    assert response.json()['cancel_requested'] is True

    monkeypatch.setattr(records, 'analyze', lambda signal: {
        'quality': {'status': 'basic_checks_passed', 'reasons': [], 'scope': 'test'},
        'waveform': [0.1, 0.2], 'sample_rate_hz': 250, 'unit': 'mV', 'duration_sec': 1,
        'heart_rate_bpm': None, 'processing_version': 'test',
        'prediction': {'status': 'model_unavailable', 'label': None, 'confidence': None,
                       'model_version': None, 'explanation': ''},
    })
    with storage.connect() as db:
        db.execute("UPDATE analysis_tasks SET status='pending' WHERE id=?", (task_id,))
    assert records.execute(task_id) is False
    owner = _owner_id('task-running')
    assert records.task_status(owner, task_id)['status'] == 'cancelled'
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM records').fetchone()[0] == 0


def _owner_id(username):
    with storage.connect() as db:
        return db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()['id']


def test_terminal_task_cannot_be_cancelled(client):
    headers = account(client, 'task-done')
    task_id = replay(client, headers)
    assert wait_task(client, headers, task_id)['status'] == 'completed'
    response = client.post(f'/api/v1/tasks/{task_id}/cancel', headers=headers)
    assert response.status_code == 409
    assert response.json()['code'] == 'task_finished'


def test_upload_idempotency_key(client, monkeypatch):
    monkeypatch.setattr(runner, 'enqueue', lambda task_id: None)
    headers = account(client, 'idempotent')
    first = upload(client, headers, key='form-submit-1')
    assert first.status_code == 202
    second = upload(client, headers, key='form-submit-1')
    assert second.status_code == 200
    assert second.json()['id'] == first.json()['id']
    third = upload(client, headers, key='form-submit-2')
    assert third.status_code == 202
    assert third.json()['id'] != first.json()['id']
    long_key = upload(client, headers, key='k' * 65)
    assert long_key.status_code == 400
    assert long_key.json()['code'] == 'invalid_request'


def test_recover_pending_and_stale_running(client):
    headers = account(client, 'task-recover')
    owner = _owner_id('task-recover')
    signal = {'samples': [0.1, 0.2], 'sample_rate_hz': 250}
    pending = records.submit(owner, signal)
    stale = records.submit(owner, signal)
    fresh = records.submit(owner, signal)
    with storage.connect() as db:
        db.execute("UPDATE analysis_tasks SET status='running', heartbeat_at='2020-01-01T00:00:00+00:00' WHERE id=?",
                   (stale['id'],))
        db.execute("UPDATE analysis_tasks SET status='running', heartbeat_at=? WHERE id=?",
                   (records._now(), fresh['id']))
    result = records.recover_tasks()
    assert pending['id'] in result['pending']
    assert stale['id'] in result['interrupted']
    assert fresh['id'] in result['interrupted']
    assert records.task_status(owner, pending['id'])['status'] == 'pending'
    interrupted = records.task_status(owner, stale['id'])
    assert interrupted['status'] == 'failed'
    assert interrupted['error_code'] == 'interrupted'
    assert records.task_status(owner, fresh['id'])['status'] == 'failed'
    assert client.get('/api/v1/tasks/' + pending['id'], headers=headers).json()['status'] == 'pending'


def test_task_events_and_summary_columns(client):
    headers = account(client, 'task-events')
    task_id = replay(client, headers)
    record = wait_task(client, headers, task_id)['record']
    with storage.connect() as db:
        statuses = [row['status'] for row in db.execute(
            'SELECT status FROM task_events WHERE task_id=? ORDER BY id', (task_id,))]
        row = db.execute('SELECT * FROM records WHERE id=?', (record['id'],)).fetchone()
    assert statuses == ['pending', 'running', 'completed']
    assert row['task_id'] == task_id
    assert row['n_samples'] == 2500
    assert row['quality_status'] == 'basic_checks_passed'
    assert row['heart_rate_bpm'] is None
    assert row['updated_at']


def test_input_error_code(client):
    headers = account(client, 'task-bad-rate')
    response = client.post('/api/v1/analyze/ecg', headers=headers,
                           files={'file': ('signal.csv', 'value\n0.1\n')},
                           data={'sample_rate_hz': '0'})
    assert response.status_code == 202
    task = wait_task(client, headers, response.json()['id'])
    assert task['status'] == 'failed'
    assert task['error_code'] == 'input_invalid'
    assert task['finished_at']


def test_multi_worker_configuration_is_rejected(monkeypatch):
    from app.main import _guard_single_process

    monkeypatch.setenv('WEB_CONCURRENCY', '2')
    with pytest.raises(RuntimeError, match='单 worker'):
        _guard_single_process()
    monkeypatch.setenv('WEB_CONCURRENCY', '1')
    _guard_single_process()
