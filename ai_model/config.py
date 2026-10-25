"""项目级 AI 环境配置加载。"""

from __future__ import annotations

import os
from pathlib import Path


_LOADED = False


def load_project_env() -> None:
    """Load AI settings from the project .env.

    AI settings in the project file are authoritative so a stale shell value
    such as ECG_EXPLANATION_PROVIDER=template cannot silently disable the
    configured explanation API.
    """
    global _LOADED
    if _LOADED:
        return
    _LOADED = True

    env_path = Path(__file__).resolve().parents[1] / '.env'
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key.startswith('ECG_') or key == 'DEEPSEEK_API_KEY':
            if value:
                os.environ[key] = value
        else:
            os.environ.setdefault(key, value)
