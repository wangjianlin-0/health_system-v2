"""Care tools use the existing family grant; every operation checks it again."""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
import re
import secrets

from app.services.records import _zone
from app.services.storage import connect


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, field):
    text = value.strip()
    if not text:
        raise ValueError(f'请填写{field}')
    return text


def _phone(value):
    phone = re.sub(r'[ .()-]', '', value.strip())
    if not re.fullmatch(r'\+?[0-9]{6,20}', phone):
        raise ValueError('请填写有效的联系电话')
    return phone


@contextmanager
def _access(user, grant_id, *, write=False, owner_only=False):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        grant = db.execute(
            """SELECT g.owner_id, g.relative_id, owner.username AS owner_name,
                      relative.username AS relative_name
               FROM grants g JOIN users owner ON owner.id=g.owner_id
               JOIN users relative ON relative.id=g.relative_id
               WHERE g.id=? AND g.active=1 AND g.status='accepted'
               AND (g.owner_id=? OR g.relative_id=?)""",
            (grant_id, user, user),
        ).fetchone()
        if not grant or (owner_only and grant['owner_id'] != user):
            raise LookupError('关怀授权不存在或无权操作')
        yield db, grant


_RECORD_FIELDS = """
    id, created_at, source, lead, duration_sec, sample_rate_hz,
    heart_rate_bpm, quality_status, quality_score, model_version,
    json_extract(payload,'$.title') AS title,
    json_extract(payload,'$.result.rate_analysis.rr_mean_ms') AS rr_mean_ms,
    json_extract(payload,'$.result.r_peak_analysis.count') AS r_peak_count,
    json_extract(payload,'$.result.safety.level') AS review_level
"""


def overview(user, grant_id, day: date, timezone_name):
    zone = _zone(timezone_name)
    first = day - timedelta(days=6)
    cutoff = datetime.combine(first, time.min, tzinfo=zone).astimezone(timezone.utc).isoformat()
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc).isoformat()
    with _access(user, grant_id) as (db, grant):
        scope = (grant['owner_id'],)
        total = db.execute('SELECT COUNT(*) FROM records WHERE owner_id=? AND supersedes_record_id IS NULL', scope).fetchone()[0]
        records = [dict(row) for row in db.execute(
            f"""SELECT {_RECORD_FIELDS} FROM records
                WHERE owner_id=? AND supersedes_record_id IS NULL
                ORDER BY created_at DESC,id DESC LIMIT 60""", scope)]
        week = {str(first + timedelta(days=i)): 0 for i in range(7)}
        for row in db.execute(
            """SELECT created_at FROM records WHERE owner_id=? AND supersedes_record_id IS NULL
               AND created_at>=? AND created_at<?""", (*scope, cutoff, end)):
            try:
                local = str(datetime.fromisoformat(row['created_at']).astimezone(zone).date())
            except (TypeError, ValueError):
                continue
            if local in week:
                week[local] += 1
        settings = db.execute('SELECT callback_phone FROM family_care_settings WHERE grant_id=?', (grant_id,)).fetchone()
        items = [dict(row) for row in db.execute(
            'SELECT id,title,due_time,done FROM family_care_items WHERE grant_id=? AND due_date=? ORDER BY due_time,id',
            (grant_id, str(day)))]
        messages = _entries(db, 'family_care_messages', grant_id, user, 'read_at', 'entry.text,')
        drills = _entries(db, 'family_care_drills', grant_id, user, 'acknowledged_at')
        contacts = [dict(row) for row in db.execute(
            'SELECT id,name,relation,phone,preferred FROM family_care_contacts WHERE grant_id=? ORDER BY preferred DESC,name,id',
            (grant_id,))]
    return {
        'owner_name': grant['owner_name'], 'relative_name': grant['relative_name'],
        'is_owner': grant['owner_id'] == user, 'records': records, 'record_count': total,
        'week': [{'date': key, 'count': value} for key, value in week.items()],
        'items': items, 'messages': messages, 'contacts': contacts, 'drills': drills,
        'callback_phone': settings['callback_phone'] if settings else None,
    }


def _entries(db, table, grant_id, user, timestamp, extra=''):
    # Table and column names are chosen by the two calls in overview, not by a request.
    return [dict(row) for row in db.execute(
        f"""SELECT entry.id, {extra} entry.created_at, entry.{timestamp},
                   entry.sender_id=? AS mine, u.username AS sender_name
            FROM {table} entry JOIN users u ON u.id=entry.sender_id
            WHERE entry.grant_id=? ORDER BY entry.created_at DESC,entry.id DESC LIMIT 100""",
        (user, grant_id))]


def add_item(user, grant_id, title, due_date, due_time):
    with _access(user, grant_id, write=True) as (db, _):
        count = db.execute(
            'SELECT COUNT(*) FROM family_care_items WHERE grant_id=? AND due_date=?',
            (grant_id, str(due_date))).fetchone()[0]
        if count >= 40:
            raise ValueError('当天最多添加 40 项照护事项')
        db.execute('INSERT INTO family_care_items VALUES(?,?,?,?,?,0)',
                   (secrets.token_hex(12), grant_id, _text(title, '事项'), str(due_date), due_time))


def set_item(user, grant_id, item_id, done):
    with _access(user, grant_id, write=True) as (db, _):
        if not db.execute('UPDATE family_care_items SET done=? WHERE grant_id=? AND id=?',
                          (int(done), grant_id, item_id)).rowcount:
            raise LookupError('事项不存在')


def send_message(user, grant_id, text):
    with _access(user, grant_id, write=True) as (db, _):
        db.execute('INSERT INTO family_care_messages VALUES(?,?,?,?,?,NULL)',
                   (secrets.token_hex(12), grant_id, user, _text(text, '留言'), _now()))


def read_message(user, grant_id, message_id):
    with _access(user, grant_id, write=True) as (db, _):
        if not db.execute(
            'UPDATE family_care_messages SET read_at=COALESCE(read_at,?) WHERE grant_id=? AND id=? AND sender_id<>?',
            (_now(), grant_id, message_id, user),
        ).rowcount:
            raise LookupError('留言不存在或无权标记已读')


def save_contact(user, grant_id, name, relation, phone):
    with _access(user, grant_id, write=True, owner_only=True) as (db, _):
        if db.execute('SELECT COUNT(*) FROM family_care_contacts WHERE grant_id=?', (grant_id,)).fetchone()[0] >= 20:
            raise ValueError('每个授权最多添加 20 位联系人')
        db.execute('INSERT INTO family_care_contacts VALUES(?,?,?,?,?,0)',
                   (secrets.token_hex(12), grant_id, _text(name, '联系人姓名'), relation.strip(), _phone(phone)))


def prefer_contact(user, grant_id, contact_id):
    with _access(user, grant_id, write=True, owner_only=True) as (db, _):
        if not db.execute('SELECT 1 FROM family_care_contacts WHERE grant_id=? AND id=?',
                          (grant_id, contact_id)).fetchone():
            raise LookupError('联系人不存在')
        db.execute('UPDATE family_care_contacts SET preferred=0 WHERE grant_id=? AND preferred=1', (grant_id,))
        db.execute('UPDATE family_care_contacts SET preferred=1 WHERE grant_id=? AND id=?', (grant_id, contact_id))


def delete_contact(user, grant_id, contact_id):
    with _access(user, grant_id, write=True, owner_only=True) as (db, _):
        if not db.execute('DELETE FROM family_care_contacts WHERE grant_id=? AND id=?',
                          (grant_id, contact_id)).rowcount:
            raise LookupError('联系人不存在')


def update_callback(user, grant_id, phone):
    with _access(user, grant_id, write=True, owner_only=True) as (db, _):
        if not phone.strip():
            db.execute('DELETE FROM family_care_settings WHERE grant_id=?', (grant_id,))
        else:
            db.execute("""INSERT INTO family_care_settings VALUES(?,?)
                       ON CONFLICT(grant_id) DO UPDATE SET callback_phone=excluded.callback_phone""",
                       (grant_id, _phone(phone)))


def send_drill(user, grant_id):
    with _access(user, grant_id, write=True) as (db, _):
        if db.execute('SELECT 1 FROM family_care_drills WHERE grant_id=? AND sender_id=? AND acknowledged_at IS NULL',
                      (grant_id, user)).fetchone():
            raise ValueError('还有一条演练等待对方确认')
        db.execute('INSERT INTO family_care_drills VALUES(?,?,?,?,NULL)', (secrets.token_hex(12), grant_id, user, _now()))


def acknowledge_drill(user, grant_id, drill_id):
    with _access(user, grant_id, write=True) as (db, _):
        if not db.execute(
            """UPDATE family_care_drills SET acknowledged_at=COALESCE(acknowledged_at,?)
               WHERE grant_id=? AND id=? AND sender_id<>?""",
            (_now(), grant_id, drill_id, user),
        ).rowcount:
            raise LookupError('演练不存在或无权确认')
