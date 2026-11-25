"""Frozen OpenECG codec-v6 ONNX adapter with full-record window analysis."""
from __future__ import annotations

import hashlib
import importlib.metadata
import math
import os
from pathlib import Path
from statistics import median
from typing import Any


class OpenEcgClassifier:
    model_version = 'openecg-codec-v6'
    window_seconds = 10
    _codec_cache = None

    def __init__(self) -> None:
        try:
            import openecg
            from openecg.deploy import OnnxCodec, bundled_codec_onnx_path
        except ImportError as exc:
            raise RuntimeError('未安装 OpenECG/ONNX Runtime，请安装 openecg[deploy]') from exc
        model_path = Path(bundled_codec_onnx_path('v6')).resolve()
        self.openecg = openecg
        self._codec_class = OnnxCodec
        self._model_path = model_path
        self.model_asset = {
            'package': 'openecg', 'package_version': importlib.metadata.version('openecg'),
            'model_version': 'codec-v6', 'backend': 'onnxruntime',
            'file_name': model_path.name, 'bytes': model_path.stat().st_size,
            'sha256': hashlib.sha256(model_path.read_bytes()).hexdigest(),
            'input_sample_rate_hz': 500, 'window_seconds': self.window_seconds,
        }

    def predict(self, processed: dict[str, Any]) -> dict[str, Any]:
        samples = [float(value) for value in processed['waveform']]
        fs = int(round(processed['sample_rate_hz']))
        if fs != 500:
            return self._unavailable('当前 OpenECG 适配器要求 500 Hz 单导联输入')
        size = fs * self.window_seconds
        if len(samples) < size:
            return {'status': 'skipped_quality', 'label': None, 'confidence': None,
                    'model_version': self.model_version, 'model_asset': self.model_asset,
                    'explanation': '记录不足 10 秒，无法完成 OpenECG 分析'}
        step_seconds = max(1, int(os.environ.get('ECG_RHYTHM_STEP_SECONDS', '5')))
        starts = list(range(0, len(samples) - size + 1, step_seconds * fs))
        if starts[-1] != len(samples) - size:
            starts.append(len(samples) - size)
        windows = [self._window(samples, start, size, fs) for start in starts]
        events = self._merge_events(windows)
        dimensions = self._dimensions(windows, events)
        primary_window = self._primary_window(windows)
        raw_label = dimensions['rhythm']['primary']
        label = {'sinus': 'normal', 'afib': 'atrial_fibrillation'}.get(
            raw_label, 'other_abnormality')
        return {
            'status': 'classified', 'label': label, 'raw_label': raw_label,
            'confidence': primary_window.get('confidence'),
            'model_version': self.model_version, 'model_asset': self.model_asset,
            'task_type': 'record_level',
            'rhythm': {'label': raw_label, 'confidence': primary_window.get('confidence'),
                       'distribution': primary_window.get('distribution', {}),
                       'conduction_flags': dimensions['conduction']['flags']},
            'rhythm_dimensions': dimensions, 'rhythm_windows': windows,
            'rhythm_events': events, 'beats': self._merge_beats(windows, fs),
            'heart_rate': self._aggregate_heart_rate(windows),
            'intervals_ms': primary_window.get('intervals_ms', {}),
            'flags': sorted({str(flag) for row in windows for flag in row.get('flags', [])}),
            'analysis_scope': {'duration_seconds': len(samples) / fs,
                               'window_seconds': self.window_seconds,
                               'step_seconds': step_seconds,
                               'windows_analyzed': len(windows),
                               'full_record_covered': True},
            'explanation': None,
        }

    def _window(self, samples: list[float], start: int, size: int, fs: int) -> dict[str, Any]:
        codec = self._codec()
        payload = self._to_dict(self.openecg.report(
            samples[start:start + size], fs=fs, model=codec))
        rhythm = payload.get('rhythm') or {}
        return {'start_sec': start / fs, 'end_sec': (start + size) / fs,
                'raw_label': str(rhythm.get('label') or 'unknown').lower(),
                'confidence': rhythm.get('confidence'),
                'distribution': rhythm.get('distribution') or {},
                'heart_rate': payload.get('heart_rate') or {},
                'beats': payload.get('beats') or {},
                'intervals_ms': payload.get('intervals_ms') or {},
                'flags': payload.get('flags') or []}

    def _codec(self):
        if OpenEcgClassifier._codec_cache is None:
            OpenEcgClassifier._codec_cache = self._codec_class(self._model_path, version='v6')
        return OpenEcgClassifier._codec_cache

    @staticmethod
    def _dimensions(windows: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
        labels = {row['raw_label'] for row in windows}
        observed = labels & {'sinus', 'afib', 'ventricular', 'paced'}
        primary = next((x for x in ('afib', 'ventricular', 'paced', 'sinus') if x in observed),
                       'unknown')
        return {
            'rhythm': {'primary': primary, 'observed': sorted(observed),
                       'events': [e for e in events if e['dimension'] == 'rhythm']},
            'conduction': {'flags': [x for x in ('avb', 'bbb') if x in labels],
                           'events': [e for e in events if e['dimension'] == 'conduction']},
            'rate': {'source': 'openecg_window_heart_rate'},
            'pacing': {'candidate': 'paced' in labels},
        }

    @staticmethod
    def _merge_events(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for row in windows:
            label = row['raw_label']
            if label == 'unknown':
                continue
            dimension = 'conduction' if label in {'avb', 'bbb'} else 'rhythm'
            if events and events[-1]['label'] == label and events[-1]['dimension'] == dimension \
                    and row['start_sec'] <= events[-1]['end_sec']:
                events[-1]['end_sec'] = max(events[-1]['end_sec'], row['end_sec'])
                events[-1]['window_count'] += 1
                events[-1]['confidence'] = max(events[-1]['confidence'] or 0,
                                               row.get('confidence') or 0)
            else:
                events.append({'dimension': dimension, 'label': label,
                               'start_sec': row['start_sec'], 'end_sec': row['end_sec'],
                               'confidence': row.get('confidence'), 'window_count': 1})
        return events

    @staticmethod
    def _primary_window(windows: list[dict[str, Any]]) -> dict[str, Any]:
        priority = {'afib': 5, 'ventricular': 4, 'paced': 3, 'sinus': 2, 'avb': 1, 'bbb': 1}
        return max(windows, key=lambda row: (priority.get(row['raw_label'], 0),
                                             row.get('confidence') or 0))

    @staticmethod
    def _aggregate_heart_rate(windows: list[dict[str, Any]]) -> dict[str, Any]:
        bpms = [row['heart_rate'].get('bpm') for row in windows]
        bpms = [float(x) for x in bpms if isinstance(x, (int, float)) and math.isfinite(x) and x > 0]
        return ({'bpm': round(float(median(bpms)), 1), 'min_bpm': min(bpms),
                 'max_bpm': max(bpms), 'window_bpms': bpms,
                 'aggregation': 'median_of_windows'} if bpms else {})

    @staticmethod
    def _merge_beats(windows: list[dict[str, Any]], fs: int) -> dict[str, Any]:
        merged: dict[int, dict[str, Any]] = {}
        for window in windows:
            offset = round(window['start_sec'] * fs)
            for event in window.get('beats', {}).get('events') or []:
                local = event.get('sample')
                if not isinstance(local, (int, float)):
                    local_time = event.get('time_sec', event.get('t_s'))
                    if not isinstance(local_time, (int, float)):
                        continue
                    local = round(local_time * fs)
                absolute = int(local) + offset
                merged.setdefault(absolute, {**event, 'sample': absolute,
                                             'time_sec': absolute / fs, 't_s': absolute / fs,
                                             'source': 'openecg_sliding_window'})
        return {'events': list(merged.values()), 'count': len(merged),
                'source': 'openecg_sliding_window'}

    @staticmethod
    def _to_dict(report: Any) -> dict[str, Any]:
        if isinstance(report, dict):
            return report
        if hasattr(report, 'to_json'):
            import json
            return json.loads(report.to_json())
        raise TypeError('OpenECG 返回结果无法转换为字典')

    def _unavailable(self, explanation: str) -> dict[str, Any]:
        return {'status': 'model_unavailable', 'label': None, 'confidence': None,
                'model_version': self.model_version,
                'model_asset': getattr(self, 'model_asset', None),
                'explanation': explanation}
