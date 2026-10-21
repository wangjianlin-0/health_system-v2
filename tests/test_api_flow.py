import pytest
import sqlite3
from fastapi.testclient import TestClient
from app.main import app
from app.services import storage
from ai_model.eval.model_eval_report import evaluate

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', tmp_path/'test.sqlite3')
    with TestClient(app) as client:
        yield client

def account(client, name):
    body = {'username':name,'password':'test-password-123'}
    assert client.post('/api/v1/auth/register',json=body).status_code == 200
    response = client.post('/api/v1/auth/login',json=body)
    assert response.status_code == 200
    return {'Authorization':'Bearer '+response.json()['token']}

def test_full_record_grant_revoke(client):
    owner, relative = account(client,'owner'), account(client,'relative')
    assert client.get('/api/v1/records').status_code == 401
    response = client.post('/api/v1/acquisition/replay',headers=owner)
    assert response.status_code == 200
    record = response.json()
    identifier = record['id']
    assert record['result']['prediction']['status'] == 'model_unavailable'
    assert record['result']['prediction']['label'] is None
    assert len(client.get('/api/v1/records',headers=owner).json()) == 1
    path = '/api/v1/records/'+identifier
    assert client.get(path,headers=relative).status_code == 404
    grant_response = client.post('/api/v1/family/grants',json={
        'username':'relative',
        'permissions':['records:list'],
    },headers=owner)
    assert grant_response.status_code == 200
    grant = grant_response.json()
    assert grant['status'] == 'pending'
    assert client.get(path,headers=relative).status_code == 404
    assert client.get('/api/v1/records?shared=true',headers=relative).json() == []

    invitations = client.get('/api/v1/family/invitations',headers=relative).json()
    assert invitations[0]['id'] == grant['id']
    assert invitations[0]['status'] == 'pending'
    assert client.post('/api/v1/family/invitations/'+grant['id']+'/accept',headers=owner).status_code == 404
    accepted = client.post('/api/v1/family/invitations/'+grant['id']+'/accept',headers=relative)
    assert accepted.status_code == 200
    assert accepted.json()['status'] == 'accepted'

    assert len(client.get('/api/v1/records?shared=true',headers=relative).json()) == 1
    assert client.get(path,headers=relative).status_code == 404
    changed = client.patch('/api/v1/family/grants/'+grant['id'],json={
        'permissions':['records:list','records:read'],
    },headers=owner)
    assert changed.status_code == 200
    assert client.get(path,headers=relative).status_code == 200

    notes = client.get('/api/v1/family/notifications',headers=relative).json()
    assert len(notes) >= 1
    assert notes[0]['status'] == 'unread'
    marked = client.patch('/api/v1/family/notifications/'+notes[0]['id'],json={'status':'read'},headers=relative)
    assert marked.status_code == 200
    assert marked.json()['status'] == 'read'
    assert client.delete('/api/v1/family/grants/'+grant['id'],headers=relative).status_code == 404
    assert client.delete('/api/v1/family/grants/'+grant['id'],headers=owner).status_code == 200
    assert client.get(path,headers=relative).status_code == 404
    assert client.get('/api/v1/records?shared=true',headers=relative).json() == []
    notes_after_revoke = client.get('/api/v1/family/notifications',headers=relative).json()
    assert notes_after_revoke[0]['kind'] == 'grant_revoked'
    assert notes_after_revoke[0]['status'] == 'unread'
    assert client.get('/api/v1/analyze/unknown',headers=owner).status_code == 404

def test_upload_bad_signal_and_validation(client):
    headers = account(client,'upload-user')
    def upload(content, name='signal.csv', rate='250'):
        return client.post('/api/v1/analyze/ecg',headers=headers,files={'file':(name,content)},data={'sample_rate_hz':rate})
    flat = upload('value\n'+'0\n'*600)
    assert flat.status_code == 200
    assert flat.json()['result']['prediction']['status'] == 'skipped_quality'
    assert upload('value\nnan\n').status_code == 400
    assert upload('time,value\n0,0.1\n').status_code == 400
    assert upload('1\n',name='signal.dat').status_code == 400
    assert upload('1\n',rate='0').status_code == 400
    assert upload('1'*2_000_001).status_code == 413
    identifier = flat.json()['id']
    storage.initialize()
    assert client.get('/api/v1/records/'+identifier,headers=headers).status_code == 200

def test_login_and_logout(client):
    body = {'username':'auth-user','password':'test-password-123'}
    assert client.post('/api/v1/auth/register',json=body).status_code == 200
    login = client.post('/api/v1/auth/login',json=body)
    assert login.status_code == 200
    assert login.json()['expires_in'] == 28800
    assert login.json()['expires_at'] > 0
    headers = {'Authorization':'Bearer '+login.json()['token']}
    session = client.get('/api/v1/auth/session',headers=headers)
    assert session.status_code == 200
    assert session.json()['username'] == 'auth-user'
    assert client.post('/api/v1/auth/login',json={'username':'auth-user','password':'wrong-password'}).status_code == 401
    assert client.post('/api/v1/auth/logout',headers=headers).status_code == 200
    assert client.get('/api/v1/records',headers=headers).status_code == 401

def test_expired_session_is_removed(client):
    headers = account(client,'expired-user')
    token = headers['Authorization'].removeprefix('Bearer ')
    with storage.connect() as db:
        db.execute('UPDATE sessions SET expires=0 WHERE token=?', (token,))
    response = client.get('/api/v1/auth/session',headers=headers)
    assert response.status_code == 401
    assert response.json()['detail'] == '登录已过期，请重新登录'
    with storage.connect() as db:
        assert db.execute('SELECT token FROM sessions WHERE token=?', (token,)).fetchone() is None

def test_invitation_decline_and_duplicate_guard(client):
    owner, relative = account(client,'invite-owner'), account(client,'invite-relative')
    body = {'username':'invite-relative','permissions':['records:list','records:read']}
    invitation = client.post('/api/v1/family/grants',json=body,headers=owner)
    assert invitation.status_code == 200
    assert client.post('/api/v1/family/grants',json=body,headers=owner).status_code == 400
    identifier = invitation.json()['id']
    declined = client.post('/api/v1/family/invitations/'+identifier+'/decline',headers=relative)
    assert declined.status_code == 200
    assert declined.json()['status'] == 'declined'
    assert client.post('/api/v1/family/invitations/'+identifier+'/accept',headers=relative).status_code == 400
    replacement = client.post('/api/v1/family/grants',json=body,headers=owner)
    assert replacement.status_code == 200
    assert replacement.json()['id'] != identifier

def test_legacy_family_schema_is_migrated(tmp_path, monkeypatch):
    database = tmp_path/'legacy.sqlite3'
    with sqlite3.connect(database) as db:
        db.executescript('''
            CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT NOT NULL);
            CREATE TABLE sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL);
            CREATE TABLE records(id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), created_at TEXT, payload TEXT);
            CREATE TABLE grants(id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id), relative_id TEXT REFERENCES users(id), active INTEGER NOT NULL);
            CREATE TABLE notifications(id TEXT PRIMARY KEY, recipient_id TEXT REFERENCES users(id), grant_id TEXT REFERENCES grants(id), message TEXT, status TEXT);
            INSERT INTO users VALUES ('owner','owner','hash'),('relative','relative','hash');
            INSERT INTO grants VALUES ('grant','owner','relative',1);
            INSERT INTO notifications VALUES ('note','relative','grant','legacy','in_app_available');
        ''')
    monkeypatch.setattr(storage, 'DB', database)
    storage.initialize()
    with storage.connect() as db:
        grant = db.execute('SELECT status,permissions FROM grants WHERE id=?', ('grant',)).fetchone()
        note = db.execute('SELECT status,kind FROM notifications WHERE id=?', ('note',)).fetchone()
    assert grant['status'] == 'accepted'
    assert grant['permissions'] == 'records:list,records:read'
    assert note['status'] == 'unread'
    assert note['kind'] == 'grant_update'

def test_real_predictions_metric():
    report = evaluate([{'true_label':'N','predicted_label':'N'},{'true_label':'V','predicted_label':'N'}])
    assert report['per_class']['V']['recall'] == 0
    assert report['per_class']['N']['precision'] == .5
    assert report['macro_f1'] == pytest.approx(1/3)
    with pytest.raises(ValueError): evaluate([])
