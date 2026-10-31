"""records 摘要列与索引：让列表、筛选、趋势不再逐条解析 payload。"""

VERSION = 2
NAME = 'record_summaries'

COLUMNS = [
    ('task_id', 'TEXT'),
    ('source', 'TEXT'),
    ('lead', 'TEXT'),
    ('unit', 'TEXT'),
    ('sample_rate_hz', 'REAL'),
    ('duration_sec', 'REAL'),
    ('n_samples', 'INTEGER'),
    ('quality_status', 'TEXT'),
    ('quality_score', 'REAL'),
    ('label', 'TEXT'),
    ('confidence', 'REAL'),
    ('heart_rate_bpm', 'REAL'),
    ('model_version', 'TEXT'),
    ('processing_version', 'TEXT'),
    ('note', 'TEXT'),
    ('input_path', 'TEXT'),
    ('input_sha256', 'TEXT'),
    ('supersedes_record_id', 'TEXT REFERENCES records(id)'),
    ('updated_at', 'TEXT'),
]

BACKFILL = '''
UPDATE records SET
  task_id            = COALESCE(json_extract(payload, '$.task_id'), task_id),
  source             = COALESCE(json_extract(payload, '$.result.source'), source),
  lead               = COALESCE(json_extract(payload, '$.result.lead'), lead),
  unit               = COALESCE(json_extract(payload, '$.result.unit'), unit),
  sample_rate_hz     = COALESCE(json_extract(payload, '$.result.sample_rate_hz'), sample_rate_hz),
  duration_sec       = COALESCE(json_extract(payload, '$.result.duration_sec'), duration_sec),
  n_samples          = COALESCE(json_array_length(payload, '$.result.waveform'), n_samples),
  quality_status     = COALESCE(json_extract(payload, '$.result.quality.status'), quality_status),
  quality_score      = COALESCE(json_extract(payload, '$.result.quality.score'), quality_score),
  label              = COALESCE(json_extract(payload, '$.result.prediction.label'), label),
  confidence         = COALESCE(json_extract(payload, '$.result.prediction.confidence'), confidence),
  heart_rate_bpm     = COALESCE(
                         json_extract(payload, '$.result.prediction.heart_rate.bpm'),
                         json_extract(payload, '$.result.heart_rate_bpm'),
                         heart_rate_bpm),
  model_version      = COALESCE(json_extract(payload, '$.result.prediction.model_version'), model_version),
  processing_version = COALESCE(json_extract(payload, '$.result.processing_version'), processing_version),
  updated_at         = COALESCE(updated_at, created_at)
WHERE payload IS NOT NULL
'''


def apply(db):
    existing = {row['name'] for row in db.execute('PRAGMA table_info(records)')}
    for name, kind in COLUMNS:
        if name not in existing:
            db.execute(f'ALTER TABLE records ADD COLUMN {name} {kind}')
    db.execute(BACKFILL)
    db.execute('CREATE INDEX IF NOT EXISTS idx_records_owner_created ON records(owner_id, created_at DESC)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_records_owner_quality ON records(owner_id, quality_status, created_at DESC)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_records_task ON records(task_id)')
