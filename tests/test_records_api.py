import time
from datetime import datetime, timedelta, timezone

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


def create_record(client, headers):
    response = client.post('/api/v1/acquisition/replay', headers=headers)
    assert response.status_code == 202
    return wait_task(client, headers, response.json()['id'])['record']


def upload_flat(client, headers):
    response = client.post('/api/v1/analyze/ecg', headers=headers,
                           files={'file': ('flat.csv', 'value\n' + '0\n' * 600)},
                           data={'sample_rate_hz': '250'})
    assert response.status_code == 202
    return wait_task(client, headers, response.json()['id'])['record']


def test_list_filters_sort_and_query(client):
    headers = account(client, 'filter-owner')
    create_record(client, headers)
    create_record(client, headers)
    upload_flat(client, headers)

    insufficient = client.get('/api/v1/records?quality=insufficient&page=1', headers=headers).json()
    assert insufficient['total'] == 1
    assert insufficient['items'][0]['quality_status'] == 'insufficient'

    everything = client.get('/api/v1/records?page=1&page_size=10&sort=created_at_asc',
                            headers=headers).json()
    assert everything['total'] == 3
    created = [item['created_at'] for item in everything['items']]
    assert created == sorted(created)
    assert client.get('/api/v1/records?sort=bogus&page=1', headers=headers).status_code == 400
    assert client.get('/api/v1/records?quality=bogus&page=1', headers=headers).status_code == 400

    today = datetime.now(timezone.utc).date().isoformat()
    bounded = client.get(f'/api/v1/records?from={today}&to={today}&page=1', headers=headers).json()
    assert bounded['total'] == 3
    assert client.get('/api/v1/records?from=not-a-date&page=1', headers=headers).status_code == 400

    record_id = everything['items'][0]['id']
    found = client.get(f'/api/v1/records?q={record_id[:6]}&page=1', headers=headers).json()
    assert found['total'] >= 1
    assert all(item['id'].startswith(record_id[:6]) for item in found['items'])


def test_list_summary_fields_and_detail_consistency(client):
    headers = account(client, 'summary-owner')
    record = create_record(client, headers)
    listed = client.get('/api/v1/records?page=1&page_size=10', headers=headers).json()['items'][0]
    assert listed['id'] == record['id']
    for key in ('source', 'sample_rate_hz', 'duration_sec', 'n_samples',
                'quality_status', 'heart_rate_bpm', 'task_id', 'owner_username'):
        assert key in listed
    assert listed['n_samples'] == 2500
    detail = client.get('/api/v1/records/' + record['id'], headers=headers).json()
    assert detail['quality_status'] == listed['quality_status'] == 'basic_checks_passed'
    assert detail['owner_username'] == 'summary-owner'
    assert detail['result']['waveform']


def test_shared_only_read(client):
    owner, relative = account(client, 'share-owner'), account(client, 'share-relative')
    record = create_record(client, owner)
    grant = client.post('/api/v1/family/grants', json={'username': 'share-relative'},
                        headers=owner).json()
    shared = client.get('/api/v1/records?shared=true&page=1&page_size=5', headers=relative).json()
    assert shared['total'] == 1
    assert shared['items'][0]['owner_username'] == 'share-owner'
    assert client.get('/api/v1/records/' + record['id'], headers=relative).status_code == 200
    assert client.delete('/api/v1/records/' + record['id'], headers=relative).status_code == 404
    assert client.get(f'/api/v1/records/{record["id"]}/export', headers=relative).status_code == 404
    client.delete('/api/v1/family/grants/' + grant['id'], headers=owner)


def test_trends_timezone_boundary_and_summary(client):
    headers = account(client, 'trend-owner')
    record = create_record(client, headers)
    now = datetime.now(timezone.utc)
    target = (now - timedelta(days=1)).replace(hour=23, minute=30, second=0, microsecond=0)
    with storage.connect() as db:
        db.execute('UPDATE records SET created_at=? WHERE id=?', (target.isoformat(), record['id']))
    local_date = (target + timedelta(hours=8)).date().isoformat()
    utc_date = target.date().isoformat()

    local = client.get('/api/v1/records/trends?days=3&timezone=Asia/Shanghai&fill=1',
                       headers=headers).json()
    assert len(local['days']) == 3
    assert local['timezone'] == 'Asia/Shanghai'
    point = next(item for item in local['days'] if item['date'] == local_date)
    assert point['records'] == 1
    assert local['summary']['total'] == 1
    assert local['summary']['insufficient'] == 0
    assert local['summary']['heart_rate_days'] == 0
    assert local['summary']['last_record_at'] == target.isoformat()

    utc = client.get('/api/v1/records/trends?days=3&timezone=UTC', headers=headers).json()
    assert next(item for item in utc['days'] if item['date'] == utc_date)['records'] == 1

    etc = client.get('/api/v1/records/trends?days=3&timezone=Etc/GMT-8', headers=headers).json()
    assert etc['timezone'] == 'Etc/GMT-8'
    assert next(item for item in etc['days'] if item['date'] == local_date)['records'] == 1
    assert client.get('/api/v1/records/trends?timezone=Nope/Zone',
                      headers=headers).status_code == 400


def test_health_reports_database_and_limits(client):
    response = client.get('/api/v1/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['database']['writable'] is True
    assert body['database']['schema_version'] >= 3
    assert body['model']['type'] == 'none'
    assert body['capabilities']['max_upload_bytes'] == 2_000_000
    assert body['tasks']['mode'] == 'inprocess'
    assert isinstance(body['tasks']['pending'], int)


def test_error_envelope_and_request_id(client):
    headers = account(client, 'envelope-owner')
    response = client.get('/api/v1/records/missing', headers=headers)
    assert response.status_code == 404
    body = response.json()
    assert body['code'] == 'record_not_found'
    assert body['detail']
    assert body['request_id'] == response.headers['X-Request-ID']

    task = client.get('/api/v1/tasks/missing', headers=headers)
    assert task.status_code == 404
    assert task.json()['code'] == 'task_not_found'

    upload = client.post('/api/v1/analyze/ecg', headers=headers,
                         files={'file': ('bad.dat', b'1')}, data={'sample_rate_hz': '250'})
    assert upload.status_code == 400
    assert upload.json()['code'] == 'invalid_request'


def test_export_csv_has_bom(client):
    headers = account(client, 'bom-owner')
    record = create_record(client, headers)
    response = client.get(f'/api/v1/records/{record["id"]}/export', headers=headers)
    assert response.status_code == 200
    assert response.content.startswith(b'\xef\xbb\xbf')
    assert 'timestamp_sec,value,sample_rate_hz' in response.text
