"""系统自检：数据库可写、迁移版本、队列深度与能力上限；不触发模型加载。"""
import os
from pathlib import Path

from fastapi import APIRouter, Response

from app.core.config import settings
from app.services.storage import connect

router = APIRouter(tags=['系统'])


@router.get('/health')
def health(response: Response):
    payload = {
        'status': 'ok',
        'version': settings.app_version,
        'database': {'writable': True, 'schema_version': None},
        'tasks': {'mode': 'inprocess', 'workers': settings.task_workers, 'pending': 0, 'running': 0},
        'model': _model_state(),
        'acquisition': 'replay_only',
        'capabilities': {
            'upload_formats': ['csv'],
            'max_upload_bytes': settings.max_upload_bytes,
            'max_samples': settings.max_samples,
            'waveform_max_points': settings.waveform_max_points,
            'timezone': _timezone_available(),
            'timezone_fallback': True,
        },
    }
    try:
        with connect() as db:
            schema_version = db.execute('PRAGMA user_version').fetchone()[0]
            payload['database']['schema_version'] = schema_version
            for row in db.execute(
                "SELECT status, COUNT(*) AS count FROM analysis_tasks "
                "WHERE status IN ('pending','running') GROUP BY status"
            ):
                payload['tasks'][row['status']] = row['count']
    except Exception:
        payload['status'] = 'degraded'
        payload['database']['writable'] = False
        response.status_code = 503
    return payload


def _model_state() -> dict:
    raw = os.environ.get('ECG_MODEL_TYPE')
    source = 'environment'
    if raw is None:
        source = 'dotenv'
        env_file = Path(__file__).resolve().parents[3] / '.env'
        try:
            for line in env_file.read_text(encoding='utf-8').splitlines():
                key, separator, value = line.partition('=')
                if separator and key.strip() == 'ECG_MODEL_TYPE':
                    raw = value.strip().strip('"').strip("'")
                    break
        except OSError:
            source = 'default'
    value = (raw or 'none').strip().lower() or 'none'
    configured = value not in {'none', 'unavailable'}
    return {'type': value, 'configured': configured, 'loaded': None, 'source': source}


def _timezone_available() -> bool:
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo('Asia/Shanghai')
        return True
    except Exception:
        return False
