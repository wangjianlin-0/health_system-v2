"""账户模块：身份、家庭协同及对应接口逻辑。"""
import hashlib
import hmac
import secrets
import time
from app.services.storage import connect

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200000).hex()
    return salt + ':' + digest

def register(username, password):
    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or len(password) < 8:
        raise ValueError('用户名不能为空，密码至少 8 位')
    with connect() as db:
        db.execute('INSERT INTO users VALUES (?,?,?)', (secrets.token_hex(12), username.strip(), password_hash(password)))
    return {'message': '注册成功，请登录'}

def login(username, password):
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not user or not hmac.compare_digest(user['password_hash'], password_hash(password, user['password_hash'].split(':')[0])):
            raise PermissionError('用户名或密码错误')
        token = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (token, user['id'], time.time()+28800))
    return {'token': token, 'username': username}

def authenticate(token):
    with connect() as db:
        row = db.execute('SELECT user_id FROM sessions WHERE token=? AND expires>?', (token, time.time())).fetchone()
    if not row:
        raise PermissionError('请登录或重新登录')
    return row['user_id']

def logout(token):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token=?', (token,))
    return {'message': '已退出'}

def grants(owner):
    _expire()
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT g.id,u.username,g.active,g.status,g.created_at,g.expires_at FROM grants g JOIN users u ON u.id=g.relative_id WHERE g.owner_id=? ORDER BY g.created_at DESC', (owner,))]


def _expire():
    with connect() as db:
        db.execute("UPDATE grants SET status='expired' WHERE status='pending' AND expires_at<=?", (time.time(),))


def invitations(user):
    _expire()
    with connect() as db:
        return [dict(r) for r in db.execute(
            'SELECT g.id,u.username,g.active,g.status,g.created_at,g.expires_at '
            'FROM grants g JOIN users u ON u.id=g.owner_id WHERE g.relative_id=? '
            'ORDER BY g.created_at DESC', (user,))]


def respond(user, identifier, accept):
    _expire()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM grants WHERE id=? AND relative_id=?', (identifier, user)).fetchone()
        if not row:
            raise LookupError('邀请不存在')
        if row['status'] != 'pending' or row['expires_at'] <= time.time():
            raise ValueError('邀请已处理、撤回或过期')
        db.execute('UPDATE grants SET active=?,status=? WHERE id=?',
                   (int(accept), 'accepted' if accept else 'declined', identifier))
    return {'message': '已接受邀请，可以查看共享记录' if accept else '已拒绝邀请'}


def leave(user, identifier):
    with connect() as db:
        row = db.execute('UPDATE grants SET active=0,status=\'revoked\' WHERE id=? AND relative_id=? AND active=1',
                         (identifier, user))
        if not row.rowcount:
            raise LookupError('共享关系不存在')
    return {'message': '已退出共享'}

def grant(owner, username):
    _expire()
    with connect() as db:
        # Serialize the duplicate check with the insert, including concurrent requests.
        db.execute('BEGIN IMMEDIATE')
        relative = db.execute('SELECT id FROM users WHERE username=?', (username.strip(),)).fetchone()
        if not relative or relative['id'] == owner:
            raise ValueError('请输入其他已注册用户的用户名')
        identifier = secrets.token_hex(12)
        if db.execute("SELECT 1 FROM grants WHERE owner_id=? AND relative_id=? AND status IN ('pending','accepted')",
                      (owner, relative['id'])).fetchone():
            raise ValueError('已存在待确认邀请或有效授权')
        db.execute('INSERT INTO grants(id,owner_id,relative_id,active,status,created_at,expires_at) VALUES (?,?,?,0,\'pending\',?,?)',
                   (identifier, owner, relative['id'], time.time(), time.time()+7*86400))
        name = db.execute('SELECT username FROM users WHERE id=?', (owner,)).fetchone()['username']
        db.execute('INSERT INTO notifications VALUES (?,?,?,?,?)', (secrets.token_hex(12), relative['id'], identifier, f'{name} 邀请你查看其心电记录，请在家庭协同页面确认', 'in_app_available'))
    return {'id': identifier, 'status': 'pending', 'message': '邀请已发送，等待对方确认'}

def revoke(owner, identifier):
    with connect() as db:
        cursor = db.execute("UPDATE grants SET active=0,status='revoked' WHERE id=? AND owner_id=?", (identifier, owner))
        if not cursor.rowcount:
            raise LookupError('授权不存在')
    return {'message': '授权已撤回'}

def notifications(user):
    _expire()
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT n.id,CASE WHEN g.status='accepted' THEN u.username || ' 已与你共享心电记录' ELSE n.message END AS message,n.status "
            "FROM notifications n JOIN grants g ON g.id=n.grant_id JOIN users u ON u.id=g.owner_id "
            "WHERE n.recipient_id=? AND g.status IN ('pending','accepted') ORDER BY g.created_at DESC", (user,))]
