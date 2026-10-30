"""业务框架配置：环境变量集中读取，启动时校验，避免散落的 os.environ。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / 'runtime' / 'health.sqlite3'
DEFAULT_UPLOAD_DIR = ROOT / 'runtime' / 'uploads'


def _int(env, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f'{name} 必须为整数') from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f'{name} 须在 {minimum}–{maximum} 之间')
    return value


def _bool(env, name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _signal_source(env) -> str:
    value = (env.get('ECG_SIGNAL_SOURCE') or 'auto').strip().lower()
    if value not in {'auto', 'table', 'payload'}:
        raise RuntimeError('ECG_SIGNAL_SOURCE 仅支持 auto/table/payload')
    return value


@dataclass(frozen=True)
class Settings:
    db_path: Path
    upload_dir: Path
    max_upload_bytes: int
    max_samples: int
    task_workers: int
    task_lease_seconds: int
    heartbeat_seconds: int
    recovery_on_start: bool
    waveform_max_points: int
    signal_source: str = 'auto'
    audit_retention_days: int = 90
    log_level: str = 'INFO'
    app_version: str = '2026.10'


def load(env=None) -> Settings:
    env = os.environ if env is None else env
    db_path = Path(env.get('HEALTH_DB_PATH') or DEFAULT_DB)
    upload_dir = Path(env.get('ECG_UPLOAD_DIR') or DEFAULT_UPLOAD_DIR)
    return Settings(
        db_path=db_path,
        upload_dir=upload_dir,
        max_upload_bytes=_int(env, 'ECG_MAX_UPLOAD_BYTES', 2_000_000, 1_000, 50_000_000),
        max_samples=_int(env, 'ECG_MAX_SAMPLES', 200_000, 2, 2_000_000),
        task_workers=_int(env, 'ECG_TASK_WORKERS', 1, 1, 8),
        task_lease_seconds=_int(env, 'ECG_TASK_LEASE_SECONDS', 120, 10, 86_400),
        heartbeat_seconds=_int(env, 'ECG_HEARTBEAT_SECONDS', 15, 2, 300),
        recovery_on_start=_bool(env, 'ECG_RECOVERY_ON_START', True),
        waveform_max_points=_int(env, 'ECG_WAVEFORM_MAX_POINTS', 8000, 100, 50_000),
        signal_source=_signal_source(env),
        audit_retention_days=_int(env, 'ECG_AUDIT_RETENTION_DAYS', 90, 0, 3650),
        log_level=(env.get('ECG_LOG_LEVEL') or 'INFO').strip().upper() or 'INFO',
    )


settings = load()
