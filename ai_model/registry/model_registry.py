"""Auditable model manifests without triggering model inference."""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _openecg() -> dict[str, Any]:
    try:
        import openecg
        path = Path(openecg.__file__).resolve().parent / 'models' / 'codec_v6_int8.onnx'
        version = importlib.metadata.version('openecg')
    except (ImportError, importlib.metadata.PackageNotFoundError):
        path, version = Path(), None
    return {
        'name': 'openecg-codec-v6', 'task': 'record_level_rhythm',
        'status': 'available' if path.is_file() else 'unavailable',
        'package_version': version, 'backend': 'onnxruntime',
        'input': {'sample_rate_hz': 500, 'unit': 'mV', 'window_seconds': 10,
                  'step_seconds_default': 5, 'leads': 1},
        'classes': ['sinus', 'avb', 'paced', 'afib', 'bbb', 'ventricular'],
        'asset': {'file_name': path.name if path.name else None,
                  'bytes': path.stat().st_size if path.is_file() else None,
                  'sha256': _sha(path)},
        'limitations': ['研究/教育用途', '单导联BBB能力受限', 'paced神经类别能力有限'],
    }


def _edge(kind: str) -> dict[str, Any]:
    is_cnn = kind == 'cnn'
    return {
        'name': 'CNN-H27-fold0' if is_cnn else 'HGB-v92-fold0',
        'task': 'beat_classification', 'status': 'configured',
        'backend': 'pytorch_subprocess' if is_cnn else 'native_exe_subprocess',
        'input': {'sample_rate_hz': 500, 'unit': 'mV', 'leads': 1,
                  'preprocess': 'hp05'},
        'classes': ['N', 'S', 'V', 'F'] if is_cnn else ['N', 'S', 'VF'],
        'fold': 0,
        'limitations': ['研究用途', '固定fold0仅用于部署',
                        'VF表示V/E/F合并而非心室颤动'] if not is_cnn else
                       ['研究用途', '固定fold0仅用于部署', 'F表示融合心拍'],
    }


def model_manifests() -> dict[str, dict[str, Any]]:
    return {
        'openecg': _openecg(), 'cnn': _edge('cnn'), 'hgb': _edge('hgb'),
        'ensemble': {
            'name': 'CNN-H27-primary+HGB-v92-review',
            'task': 'beat_classification_review', 'status': 'configured',
            'backend': 'two_isolated_subprocesses',
            'input': {'sample_rate_hz': 500, 'unit': 'mV', 'leads': 1,
                      'preprocess': 'hp05'},
            'classes': ['N', 'S', 'V', 'F'],
            'policy': 'CNN primary; HGB consistency review; no fused probability',
            'limitations': ['运行时延约为两个模型之和', '不一致结果需人工复核'],
        },
    }


def verify_model_manifests() -> dict[str, Any]:
    manifests = model_manifests()
    errors = []
    openecg = manifests['openecg']
    if openecg['status'] == 'available' and not openecg['asset']['sha256']:
        errors.append('OpenECG asset hash missing')
    return {'passed': not errors, 'errors': errors, 'models': manifests}
