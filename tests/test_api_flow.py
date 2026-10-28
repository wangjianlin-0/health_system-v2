import time

import pytest

from ai_model.eval.model_eval_report import evaluate
from app.services import storage


def account(client, name):
    body = {'username': name, 'password': 'test-password-123'}
    assert client.post('/api/v1/auth/register', json=body).status_code == 200
    response = client.post('/api/v1/auth/login', json=body)
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


def wait_task(client, headers, task_id, timeout=10):
    deadline = time.time() + timeout
    task = None
    while time.time() < deadline:
        response = client.get('/api/v1/tasks/' + task_id, headers=headers)
        assert response.status_code == 200
        task = response.json()
        if task['status'] in ('completed', 'failed', 'cancelled'):
            return task
        time.sleep(0.02)
    raise AssertionError(f'任务未在 {timeout}s 内结束：{task_id}，最后状态 {task and task["status"]}')


def test_full_record_grant_revoke(client):
    owner, relative = account(client, 'owner'), account(client, 'relative')
    assert client.get('/api/v1/records').status_code == 401
    response = client.post('/api/v1/acquisition/replay', headers=owner)
    assert response.status_code == 202
    task_id = response.json()['id']
    status = wait_task(client, owner, task_id)
    assert status['status'] == 'completed'
    assert status['stage'] == 'finished'
    assert status['record_id']
    assert client.get('/api/v1/tasks/' + task_id, headers=relative).status_code == 404
    record = status['record']
    identifier = record['id']
    assert record['result']['prediction']['status'] == 'model_unavailable'
    assert record['result']['prediction']['label'] is None
    assert record['quality_status'] == 'basic_checks_passed'
    assert record['sample_rate_hz'] == 250
    assert len(client.get('/api/v1/records', headers=owner).json()) == 1
    path = '/api/v1/records/' + identifier
    assert client.get(path, headers=relative).status_code == 404
    grant = client.post('/api/v1/family/grants', json={'username': 'relative'}, headers=owner).json()
    assert client.get(path, headers=relative).status_code == 200
    assert len(client.get('/api/v1/records?shared=true', headers=relative).json()) == 1
    shared = client.get('/api/v1/records?shared=true&page=1&page_size=10', headers=relative).json()
    assert shared['items'][0]['owner_username'] == 'owner'
    assert len(client.get('/api/v1/family/notifications', headers=relative).json()) == 1
    assert client.delete('/api/v1/family/grants/' + grant['id'], headers=relative).status_code == 404
    assert client.delete('/api/v1/family/grants/' + grant['id'], headers=owner).status_code == 200
    assert client.get(path, headers=relative).status_code == 404
    assert client.get('/api/v1/records?shared=true', headers=relative).json() == []
    assert client.get('/api/v1/family/notifications', headers=relative).json() == []
    assert client.get('/api/v1/analyze/unknown', headers=owner).status_code == 404


def test_upload_bad_signal_and_validation(client):
    headers = account(client, 'upload-user')

    def upload(content, name='signal.csv', rate='250'):
        return client.post('/api/v1/analyze/ecg', headers=headers,
                           files={'file': (name, content)}, data={'sample_rate_hz': rate})

    flat = upload('value\n' + '0\n' * 600)
    assert flat.status_code == 202
    flat_task = wait_task(client, headers, flat.json()['id'])
    assert flat_task['status'] == 'completed'
    flat_record = flat_task['record']
    assert flat_record['result']['prediction']['status'] == 'skipped_quality'
    assert flat_record['quality_status'] == 'insufficient'

    bad = upload('value\nnan\n')
    assert bad.status_code == 202
    bad_task = wait_task(client, headers, bad.json()['id'])
    assert bad_task['status'] == 'failed'
    assert bad_task['error_code'] == 'input_invalid'
    assert '非有限值' in bad_task['error']

    assert upload('time,value\n0,0.1\n').status_code == 400
    assert upload('1\n', name='signal.dat').status_code == 400
    bad_rate = upload('1\n', rate='0')
    assert wait_task(client, headers, bad_rate.json()['id'])['status'] == 'failed'
    assert upload('1' * 2_000_001).status_code == 413

    identifier = flat_record['id']
    storage.initialize()
    assert client.get('/api/v1/records/' + identifier, headers=headers).status_code == 200


def test_login_and_logout(client):
    headers = account(client, 'auth-user')
    assert client.post('/api/v1/auth/login',
                       json={'username': 'auth-user', 'password': 'wrong-password'}).status_code == 401
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 200
    assert client.get('/api/v1/records', headers=headers).status_code == 401


def test_real_predictions_metric():
    report = evaluate([{'true_label': 'N', 'predicted_label': 'N'},
                       {'true_label': 'V', 'predicted_label': 'N'}])
    assert report['per_class']['V']['recall'] == 0
    assert report['per_class']['N']['precision'] == .5
    assert report['macro_f1'] == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        evaluate([])


def test_task_failure_and_restart(client, monkeypatch):
    from app.services import records

    headers = account(client, 'task-owner')
    other = account(client, 'other-owner')
    assert client.get('/api/v1/tasks/unknown', headers=headers).status_code == 404

    def fail(signal):
        raise RuntimeError('inference failed')

    monkeypatch.setattr(records, 'analyze', fail)
    response = client.post('/api/v1/acquisition/replay', headers=headers)
    task_id = response.json()['id']
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'failed'
    assert task['error_code'] == 'analysis_failed'
    assert 'inference failed' in task['error']
    assert task['record_id'] is None
    assert client.get('/api/v1/tasks/' + task_id, headers=other).status_code == 404

    with storage.connect() as db:
        owner = db.execute('SELECT id FROM users WHERE username=?', ('task-owner',)).fetchone()['id']
    pending = records.submit(owner, {'samples': [1, 2], 'sample_rate_hz': 250})
    running = records.submit(owner, {'samples': [1, 2], 'sample_rate_hz': 250})
    with storage.connect() as db:
        db.execute("UPDATE analysis_tasks SET status='running' WHERE id=?", (running['id'],))
    recovered = records.recover_tasks()
    assert pending['id'] in recovered['pending']
    assert records.task_status(owner, pending['id'])['status'] == 'pending'
    interrupted = records.task_status(owner, running['id'])
    assert interrupted['status'] == 'failed'
    assert interrupted['error_code'] == 'interrupted'
    assert records.task_status(owner, task_id)['error'] == 'RuntimeError: inference failed'


def test_submission_is_pending_until_background_execution(client, monkeypatch):
    from app.core.runner import runner
    from app.services import records

    headers = account(client, 'pending-owner')
    monkeypatch.setattr(runner, 'enqueue', lambda task_id: None)
    response = client.post('/api/v1/acquisition/replay', headers=headers)
    assert response.status_code == 202
    task_id = response.json()['id']
    task = client.get('/api/v1/tasks/' + task_id, headers=headers).json()
    assert task['status'] == 'pending'
    assert task['record_id'] is None
    assert client.get('/api/v1/records', headers=headers).json() == []
    records.execute(task_id)
    records.execute(task_id)  # duplicate delivery must not create a second record
    assert client.get('/api/v1/tasks/' + task_id, headers=headers).json()['status'] == 'completed'
    assert len(client.get('/api/v1/records', headers=headers).json()) == 1


def test_history_pagination_trends_export_and_owner_delete(client):
    owner, relative = account(client, 'history-owner'), account(client, 'history-relative')
    task_ids = []
    for _ in range(12):
        response = client.post('/api/v1/acquisition/replay', headers=owner)
        assert response.status_code == 202
        task_ids.append(response.json()['id'])
    for task_id in task_ids:
        assert wait_task(client, owner, task_id)['status'] == 'completed'

    page = client.get('/api/v1/records?page=2&page_size=5', headers=owner)
    assert page.status_code == 200
    assert page.json()['total'] == 12
    assert page.json()['pages'] == 3
    assert len(page.json()['items']) == 5
    assert page.json()['items'][0]['quality_status'] == 'basic_checks_passed'
    assert client.get('/api/v1/records?page=0', headers=owner).status_code == 422
    trend = client.get('/api/v1/records/trends?days=30', headers=owner).json()
    assert sum(point['records'] for point in trend['days']) == 12
    assert all(point['heart_rate_bpm'] is None for point in trend['days'])
    assert trend['summary']['total'] == 12
    task = client.get('/api/v1/tasks/' + task_ids[0], headers=owner).json()
    record_id = task['record_id']
    exported = client.get(f'/api/v1/records/{record_id}/export', headers=owner)
    assert exported.status_code == 200
    assert 'timestamp_sec,value,sample_rate_hz' in exported.text
    assert client.get(f'/api/v1/records/{record_id}/export?format=json',
                      headers=owner).json()['id'] == record_id
    grant = client.post('/api/v1/family/grants', json={'username': 'history-relative'},
                        headers=owner).json()
    assert client.get(f'/api/v1/records/{record_id}', headers=relative).status_code == 200
    assert client.get(f'/api/v1/records/{record_id}/export', headers=relative).status_code == 404
    assert client.delete(f'/api/v1/records/{record_id}', headers=relative).status_code == 404
    assert client.delete(f'/api/v1/records/{record_id}', headers=owner).status_code == 200
    assert client.get(f'/api/v1/records/{record_id}', headers=owner).status_code == 404
    assert client.get('/api/v1/tasks/' + task_ids[0], headers=owner).status_code == 404
    assert client.get('/api/v1/records?page=1&page_size=20', headers=owner).json()['total'] == 11
    assert client.delete('/api/v1/family/grants/' + grant['id'], headers=owner).status_code == 200
