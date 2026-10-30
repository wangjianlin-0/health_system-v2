"""Adapter for the single-lead 500 Hz OpenECG codec."""

from __future__ import annotations

from typing import Any


class OpenEcgClassifier:
    model_version = 'openecg-codec-v6'

    def __init__(self) -> None:
        try:
            import openecg
        except ImportError as exc:
            raise RuntimeError('未安装 OpenECG，请安装 openecg[report]') from exc
        self.openecg = openecg

    def predict(self, processed: dict[str, Any]) -> dict[str, Any]:
        samples = [float(value) for value in processed['waveform']]
        sample_rate = int(round(processed['sample_rate_hz']))
        if sample_rate != 500:
            return self._unavailable('当前 OpenECG 适配器要求 500 Hz 单导联输入')
        if len(samples) < sample_rate * 10:
            return {
                'status': 'skipped_quality',
                'label': None,
                'confidence': None,
                'model_version': self.model_version,
                'explanation': '记录不足 10 秒，无法完成 OpenECG 分析',
            }

        report = self.openecg.report(samples[:sample_rate * 10], fs=sample_rate)
        payload = self._to_dict(report)
        rhythm = payload.get('rhythm') or {}
        raw_label = rhythm.get('label')
        label = {
            'sinus': 'normal',
            'afib': 'atrial_fibrillation',
            'avb': 'other_abnormality',
            'bbb': 'other_abnormality',
            'ventricular': 'other_abnormality',
            'paced': 'other_abnormality',
        }.get(raw_label, 'other_abnormality')
        return {
            'status': 'classified',
            'label': label,
            'raw_label': raw_label,
            'confidence': rhythm.get('confidence'),
            'model_version': self.model_version,
            'task_type': 'record_level',
            'rhythm': rhythm,
            'beats': payload.get('beats', {}),
            'heart_rate': payload.get('heart_rate', {}),
            'intervals_ms': payload.get('intervals_ms', {}),
            'flags': payload.get('flags', []),
            'explanation': None,
        }

    @staticmethod
    def _to_dict(report: Any) -> dict[str, Any]:
        if isinstance(report, dict):
            return report
        if hasattr(report, 'to_json'):
            import json
            return json.loads(report.to_json())
        raise TypeError('OpenECG 返回结果无法转换为字典')

    def _unavailable(self, explanation: str) -> dict[str, Any]:
        return {
            'status': 'model_unavailable',
            'label': None,
            'confidence': None,
            'model_version': self.model_version,
            'explanation': explanation,
        }
