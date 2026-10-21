"""王书阁：记录业务、分析任务编排与持久化。当前采用同步任务。"""
import json
import secrets
from datetime import datetime, timezone
from ai_model.pipeline import analyze
from app.services.storage import connect

def create(user, signal):
    result = analyze(signal)
    record = {'id': secrets.token_hex(12), 'created_at': datetime.now(timezone.utc).isoformat(), 'task_status': 'completed', 'result': result}
    with connect() as db:
        db.execute('INSERT INTO records VALUES (?,?,?,?)', (record['id'], user, record['created_at'], json.dumps(record)))
    return record

def list_records(user, shared=False):
    with connect() as db:
        if shared:
            rows = db.execute('''
                SELECT DISTINCT r.id,r.created_at,r.owner_id FROM records r
                JOIN grants g ON g.owner_id=r.owner_id
                WHERE g.relative_id=? AND g.active=1 AND g.status='accepted'
                  AND (',' || g.permissions || ',') LIKE '%,records:list,%'
                ORDER BY r.created_at DESC
            ''', (user,))
        else:
            rows = db.execute('SELECT id,created_at FROM records WHERE owner_id=? ORDER BY created_at DESC', (user,))
        return [dict(r) for r in rows]

def detail(user, identifier):
    with connect() as db:
        row = db.execute('''
            SELECT * FROM records WHERE id=? AND (
                owner_id=? OR EXISTS (
                    SELECT 1 FROM grants g
                    WHERE g.owner_id=records.owner_id AND g.relative_id=?
                      AND g.active=1 AND g.status='accepted'
                      AND (',' || g.permissions || ',') LIKE '%,records:read,%'
                )
            )
        ''', (identifier,user,user)).fetchone()
    if not row:
        raise LookupError('记录不存在或没有查看权限')
    return json.loads(row['payload'])
