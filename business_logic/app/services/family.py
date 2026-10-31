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
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT g.id,u.username,g.active FROM grants g JOIN users u ON u.id=g.relative_id WHERE g.owner_id=?', (owner,))]

def grant(owner, username):
    with connect() as db:
        relative = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        if not relative or relative['id'] == owner:
            raise ValueError('请输入其他已注册用户的用户名')
        identifier = secrets.token_hex(12)
        db.execute('INSERT INTO grants VALUES (?,?,?,1)', (identifier, owner, relative['id']))
        db.execute('INSERT INTO notifications VALUES (?,?,?,?,?)', (secrets.token_hex(12), relative['id'], identifier, '一位用户已向你开放记录查看权限', 'in_app_available'))
    return {'id': identifier, 'message': '授权已建立；仅开放记录查看'}

def revoke(owner, identifier):
    with connect() as db:
        cursor = db.execute('UPDATE grants SET active=0 WHERE id=? AND owner_id=?', (identifier, owner))
        if not cursor.rowcount:
            raise LookupError('授权不存在')
    return {'message': '授权已撤回'}

def notifications(user):
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT n.id,n.message,n.status FROM notifications n JOIN grants g ON g.id=n.grant_id WHERE n.recipient_id=? AND g.active=1', (user,))]
