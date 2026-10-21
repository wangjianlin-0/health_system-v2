"""李运嘉：身份、家庭协同及对应接口逻辑。"""
import hashlib
import hmac
import secrets
import time
from app.services.storage import connect

SESSION_SECONDS = 8 * 60 * 60
ALLOWED_PERMISSIONS = {'records:list', 'records:read'}

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
        user = db.execute('SELECT * FROM users WHERE username=?', (username.strip(),)).fetchone()
        if not user or not hmac.compare_digest(user['password_hash'], password_hash(password, user['password_hash'].split(':')[0])):
            raise PermissionError('用户名或密码错误')
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + SESSION_SECONDS
        db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (token, user['id'], expires_at))
    return {'token': token, 'username': user['username'], 'expires_at': expires_at, 'expires_in': SESSION_SECONDS}

def authenticate(token):
    expired = False
    with connect() as db:
        row = db.execute('SELECT user_id,expires FROM sessions WHERE token=?', (token,)).fetchone()
        if row and row['expires'] <= time.time():
            db.execute('DELETE FROM sessions WHERE token=?', (token,))
            expired = True
    if expired:
        raise PermissionError('登录已过期，请重新登录')
    if not row:
        raise PermissionError('请登录或重新登录')
    return row['user_id']

def session_info(token):
    authenticate(token)
    with connect() as db:
        row = db.execute('''
            SELECT u.id,u.username,s.expires
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token=?
        ''', (token,)).fetchone()
    return {'user_id': row['id'], 'username': row['username'], 'expires_at': row['expires']}

def logout(token):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token=?', (token,))
    return {'message': '已退出'}

def grants(owner):
    with connect() as db:
        rows = db.execute('''
            SELECT g.id,u.username,g.active,g.status,g.permissions,g.created_at,g.responded_at
            FROM grants g JOIN users u ON u.id=g.relative_id
            WHERE g.owner_id=? ORDER BY g.created_at DESC
        ''', (owner,))
        return [_grant_row(row) for row in rows]

def invitations(relative):
    with connect() as db:
        rows = db.execute('''
            SELECT g.id,u.username AS owner_username,g.status,g.permissions,g.created_at,g.responded_at
            FROM grants g JOIN users u ON u.id=g.owner_id
            WHERE g.relative_id=? AND g.status IN ('pending','accepted','declined')
            ORDER BY g.created_at DESC
        ''', (relative,))
        return [{**dict(row), 'permissions': _permission_list(row['permissions'])} for row in rows]

def _permission_list(value):
    return [item for item in (value or '').split(',') if item]

def _normalize_permissions(permissions):
    requested = set(permissions or ['records:list', 'records:read'])
    if not requested or not requested <= ALLOWED_PERMISSIONS:
        raise ValueError('权限仅支持 records:list 和 records:read')
    if 'records:read' in requested:
        requested.add('records:list')
    return ','.join(sorted(requested))

def _grant_row(row):
    result = dict(row)
    result['permissions'] = _permission_list(result['permissions'])
    return result

def _notify(db, recipient, grant_id, message, kind):
    db.execute(
        'INSERT INTO notifications(id,recipient_id,grant_id,message,status,kind,created_at,read_at) VALUES (?,?,?,?,?,?,?,NULL)',
        (secrets.token_hex(12), recipient, grant_id, message, 'unread', kind, time.time()),
    )

def grant(owner, username, permissions=None):
    normalized_permissions = _normalize_permissions(permissions)
    with connect() as db:
        relative = db.execute('SELECT id,username FROM users WHERE username=?', (username.strip(),)).fetchone()
        if not relative or relative['id'] == owner:
            raise ValueError('请输入其他已注册用户的用户名')
        duplicate = db.execute('''
            SELECT id FROM grants
            WHERE owner_id=? AND relative_id=? AND status IN ('pending','accepted')
        ''', (owner, relative['id'])).fetchone()
        if duplicate:
            raise ValueError('该用户已有待处理邀请或有效授权')
        identifier = secrets.token_hex(12)
        created_at = time.time()
        db.execute('''
            INSERT INTO grants(id,owner_id,relative_id,active,status,permissions,created_at,responded_at)
            VALUES (?,?,?,0,'pending',?,?,NULL)
        ''', (identifier, owner, relative['id'], normalized_permissions, created_at))
        _notify(db, relative['id'], identifier, '你收到一条家庭记录查看邀请，请确认是否接受', 'grant_invitation')
    return {'id': identifier, 'status': 'pending', 'permissions': _permission_list(normalized_permissions), 'message': '邀请已发送，等待对方确认'}

def respond(relative, identifier, decision):
    if decision not in {'accepted', 'declined'}:
        raise ValueError('邀请只能接受或拒绝')
    with connect() as db:
        invitation = db.execute('SELECT * FROM grants WHERE id=? AND relative_id=?', (identifier, relative)).fetchone()
        if not invitation:
            raise LookupError('邀请不存在')
        if invitation['status'] != 'pending':
            raise ValueError('邀请已经处理')
        db.execute(
            'UPDATE grants SET status=?,active=?,responded_at=? WHERE id=?',
            (decision, 1 if decision == 'accepted' else 0, time.time(), identifier),
        )
        text = '对方已接受家庭记录查看邀请' if decision == 'accepted' else '对方已拒绝家庭记录查看邀请'
        _notify(db, invitation['owner_id'], identifier, text, f'grant_{decision}')
    return {'id': identifier, 'status': decision, 'message': '邀请已接受' if decision == 'accepted' else '邀请已拒绝'}

def update_permissions(owner, identifier, permissions):
    normalized_permissions = _normalize_permissions(permissions)
    with connect() as db:
        row = db.execute('SELECT relative_id,status FROM grants WHERE id=? AND owner_id=?', (identifier, owner)).fetchone()
        if not row or row['status'] not in {'pending', 'accepted'}:
            raise LookupError('待处理邀请或有效授权不存在')
        db.execute('UPDATE grants SET permissions=? WHERE id=?', (normalized_permissions, identifier))
        _notify(db, row['relative_id'], identifier, '家庭记录查看权限范围已更新', 'grant_permissions_updated')
    return {'id': identifier, 'permissions': _permission_list(normalized_permissions), 'message': '权限范围已更新'}

def revoke(owner, identifier):
    with connect() as db:
        row = db.execute('SELECT relative_id,status FROM grants WHERE id=? AND owner_id=?', (identifier, owner)).fetchone()
        if not row or row['status'] not in {'pending', 'accepted'}:
            raise LookupError('授权不存在')
        db.execute("UPDATE grants SET active=0,status='revoked',responded_at=? WHERE id=?", (time.time(), identifier))
        _notify(db, row['relative_id'], identifier, '家庭记录查看邀请或授权已撤回', 'grant_revoked')
    return {'message': '授权已撤回'}

def notifications(user):
    with connect() as db:
        return [dict(row) for row in db.execute('''
            SELECT id,grant_id,message,status,kind,created_at,read_at
            FROM notifications WHERE recipient_id=? ORDER BY created_at DESC
        ''', (user,))]

def update_notification(user, identifier, status):
    if status not in {'read', 'dismissed'}:
        raise ValueError('通知状态仅支持 read 或 dismissed')
    with connect() as db:
        cursor = db.execute(
            'UPDATE notifications SET status=?,read_at=? WHERE id=? AND recipient_id=?',
            (status, time.time(), identifier, user),
        )
        if not cursor.rowcount:
            raise LookupError('通知不存在')
    return {'id': identifier, 'status': status}
