"""ECGFounder adapter with explicit input and weight validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ECGFounderClassifier:
    model_version = 'ecgfounder-unavailable'

    def __init__(self, model_path: str = '') -> None:
        root = Path(__file__).resolve().parents[1] / 'models' / 'ecg_founder'
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        self.manifest = manifest
        self.channels = int(manifest['input']['channels'])
        self.sample_rate = int(manifest['input']['sample_rate'])
        self.duration_sec = int(manifest['input']['duration_sec'])
        configured_path = model_path or os.environ.get('ECGFOUNDER_WEIGHTS', '')
        self.model_path = Path(configured_path) if configured_path else root / 'weights'
        self.model_version = f"ecgfounder-{manifest.get('version', 'unknown')}"
        if self.channels != 1:
            raise RuntimeError(
                f'当前 ECGFounder manifest 要求 {self.channels} 导联，不能用单导联复制或补零'
            )
        if manifest.get('status') != 'ready':
            raise RuntimeError('ECGFounder 权重尚未就绪，请先放入官方权重并核对 manifest')
        if not self.model_path.exists():
            raise RuntimeError(f'ECGFounder 权重路径不存在: {self.model_path}')
        try:
            import tensorflow as tf
        except ImportError as exc:
            raise RuntimeError('ECGFounder 需要安装 tensorflow') from exc
        self.model = tf.saved_model.load(str(self.model_path))

    def predict(self, processed: dict[str, Any]) -> dict[str, Any]:
        import numpy as np

        samples = np.asarray(processed['waveform'], dtype=np.float32)
        rate = int(round(processed['sample_rate_hz']))
        expected = self.sample_rate * self.duration_sec
        if rate != self.sample_rate or samples.size < expected:
            return self._unavailable('ECGFounder 输入采样率或记录时长不符合要求')
        output = self.model(samples[:expected].reshape(1, expected, 1))
        scores = np.asarray(output.numpy() if hasattr(output, 'numpy') else output).reshape(-1)
        index = int(scores.argmax())
        labels = self.manifest.get('output', {}).get('labels', [])
        raw_label = labels[index] if index < len(labels) else str(index)
        return {
            'status': 'classified', 'label': self._map_label(raw_label),
            'raw_label': raw_label, 'confidence': float(scores[index]),
            'model_version': self.model_version, 'task_type': 'record_level',
            'explanation': None,
        }

    @staticmethod
    def _map_label(raw_label: str) -> str:
        value = raw_label.upper()
        if value in {'NORM', 'SINUS', 'NORMAL'}:
            return 'normal'
        if value in {'AFIB', 'ATRIAL_FIBRILLATION'}:
            return 'atrial_fibrillation'
        return 'other_abnormality'

    def _unavailable(self, explanation: str) -> dict[str, Any]:
        return {'status': 'model_unavailable', 'label': None, 'confidence': None,
                'model_version': self.model_version, 'explanation': explanation}
