"""波形外置：record_signals 保存压缩 float32，payload 只保留结果。"""
import json
import struct
import zlib

VERSION = 4
NAME = 'waveform_store'

ENCODING = 'f32le+zlib'


def apply(db):
    db.execute('''CREATE TABLE IF NOT EXISTS record_signals(
        record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
        sample_rate_hz REAL NOT NULL,
        unit TEXT NOT NULL,
        n_samples INTEGER NOT NULL,
        encoding TEXT NOT NULL,
        data BLOB NOT NULL)''')
    rows = db.execute("SELECT id, payload FROM records WHERE payload IS NOT NULL").fetchall()
    for row in rows:
        try:
            payload = json.loads(row['payload'])
        except (TypeError, ValueError):
            continue
        result = payload.get('result')
        if not isinstance(result, dict):
            continue
        waveform = result.get('waveform')
        if not isinstance(waveform, list) or not waveform:
            continue
        values = [float(value) for value in waveform]
        data = zlib.compress(struct.pack(f'<{len(values)}f', *values))
        db.execute(
            'INSERT OR REPLACE INTO record_signals(record_id, sample_rate_hz, unit, n_samples, encoding, data) '
            'VALUES (?,?,?,?,?,?)',
            (row['id'], float(result.get('sample_rate_hz') or 0), result.get('unit') or 'mV',
             len(values), ENCODING, data),
        )
        result.pop('waveform', None)
        payload['result'] = result
        db.execute('UPDATE records SET payload=?, n_samples=COALESCE(n_samples, ?) WHERE id=?',
                   (json.dumps(payload, ensure_ascii=False), len(values), row['id']))
