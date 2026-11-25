import time
import shutil

from app.services import storage
from app.services import migrations
from test_api_flow import account


def invite(client, owner, username):
    response = client.post('/api/v1/family/grants', headers=owner, json={'username': username})
    assert response.status_code == 200
    assert response.json()['status'] == 'pending'
    return response.json()['id']


def respond(client, relative, identifier, accept=True):
    return client.post(f'/api/v1/family/invitations/{identifier}/respond', headers=relative, json={'accept': accept})


def test_only_invitee_can_accept_and_permission_ends_on_leave(client):
    owner, relative, other = [account(client, name) for name in ('invite-owner', 'invite-relative', 'invite-other')]
    identifier = invite(client, owner, 'invite-relative')
    assert client.get('/api/v1/family/invitations', headers=relative).json()[0]['username'] == 'invite-owner'
    assert client.get('/api/v1/family/invitations', headers=other).json() == []
    assert respond(client, owner, identifier).status_code == 404
    assert respond(client, other, identifier).status_code == 404
    with storage.connect() as db:
        assert db.execute('SELECT active FROM grants WHERE id=?', (identifier,)).fetchone()['active'] == 0
    assert respond(client, relative, identifier).status_code == 200
    assert respond(client, relative, identifier).status_code == 400
    assert client.get('/api/v1/family/grants', headers=owner).json()[0]['status'] == 'accepted'
    assert client.delete(f'/api/v1/family/invitations/{identifier}', headers=other).status_code == 404
    assert client.delete(f'/api/v1/family/invitations/{identifier}', headers=relative).status_code == 200
    with storage.connect() as db:
        assert db.execute('SELECT active FROM grants WHERE id=?', (identifier,)).fetchone()['active'] == 0
    assert client.get('/api/v1/family/notifications', headers=relative).json() == []


def test_decline_reinvite_duplicate_and_revoke_pending(client):
    owner, relative = account(client, 'decline-owner'), account(client, 'decline-relative')
    identifier = invite(client, owner, 'decline-relative')
    assert client.post('/api/v1/family/grants', headers=owner, json={'username': 'decline-relative'}).status_code == 400
    assert respond(client, relative, identifier, False).status_code == 200
    assert client.get('/api/v1/family/grants', headers=owner).json()[0]['status'] == 'declined'
    assert client.get('/api/v1/family/notifications', headers=relative).json() == []
    new_id = invite(client, owner, 'decline-relative')
    assert client.delete(f'/api/v1/family/grants/{new_id}', headers=owner).status_code == 200
    assert respond(client, relative, new_id).status_code == 400


def test_expiry_cannot_be_accepted_and_allows_new_invitation(client):
    owner, relative = account(client, 'expiry-owner'), account(client, 'expiry-relative')
    identifier = invite(client, owner, 'expiry-relative')
    with storage.connect() as db:
        db.execute('UPDATE grants SET expires_at=? WHERE id=?', (time.time()-1, identifier))
    assert respond(client, relative, identifier).status_code == 400
    assert client.get('/api/v1/family/invitations', headers=relative).json()[0]['status'] == 'expired'
    assert client.get('/api/v1/family/notifications', headers=relative).json() == []
    invite(client, owner, 'expiry-relative')


def test_invitation_requires_real_other_user_and_authentication(client):
    owner = account(client, 'self-owner')
    for username in ('self-owner', 'missing-user', '   '):
        assert client.post('/api/v1/family/grants', headers=owner, json={'username': username}).status_code == 400
    assert client.get('/api/v1/family/invitations').status_code == 401


def test_upgrade_preserves_existing_grants(tmp_path, monkeypatch):
    old_migrations = tmp_path / 'old_migrations'
    old_migrations.mkdir()
    for path in migrations.MIGRATIONS_DIR.glob('000[1-5]_*.py'):
        shutil.copy2(path, old_migrations / path.name)
    monkeypatch.setattr(storage, 'DB', tmp_path / 'legacy-family.sqlite3')
    with storage.connect() as db:
        migrations.run_migrations(db, old_migrations)
        db.execute("INSERT INTO users VALUES ('owner','owner','hash')")
        db.execute("INSERT INTO users VALUES ('relative','relative','hash')")
        db.execute("INSERT INTO grants VALUES ('existing','owner','relative',1)")
        db.execute("INSERT INTO grants VALUES ('revoked','owner','relative',0)")
    storage.initialize()
    with storage.connect() as db:
        grants = {r['id']: dict(r) for r in db.execute('SELECT * FROM grants')}
    assert grants['existing']['active'] == 1
    assert grants['existing']['status'] == 'accepted'
    assert grants['revoked']['active'] == 0
    assert grants['revoked']['status'] == 'revoked'
