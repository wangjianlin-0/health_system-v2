"""Convert model output into traceable, named ECG concepts."""

from __future__ import annotations

from typing import Any


def _concept(name: str, label: str, activation: float, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        'name': name,
        'label': label,
        'activation': round(max(0.0, min(1.0, activation)), 3),
        'evidence': evidence,
    }


def build_concepts(prediction: dict[str, Any], quality: dict[str, Any]) -> list[dict[str, Any]]:
    concepts: list[dict[str, Any]] = []
    if quality.get('status') == 'insufficient':
        return [_concept('poor_signal_quality', '信号质量不足', 1.0, {
            'reasons': quality.get('reasons', []),
        })]

    for flag in prediction.get('flags', []):
        concepts.append(_concept(f'flag_{flag}', str(flag), 1.0, {'source': 'openecg_flag'}))

    heart_rate = prediction.get('heart_rate') or {}
    bpm = heart_rate.get('bpm')
    if isinstance(bpm, (int, float)):
        if bpm > 100:
            concepts.append(_concept('fast_rate', '心率偏快', min(1.0, (bpm - 100) / 40), {'bpm': bpm}))
        elif bpm < 60:
            concepts.append(_concept('slow_rate', '心率偏慢', min(1.0, (60 - bpm) / 30), {'bpm': bpm}))

    rr_cv = heart_rate.get('rr_cv')
    if isinstance(rr_cv, (int, float)):
        if rr_cv >= 0.12:
            concepts.append(_concept('irregular_rr', 'RR 间期不规则', min(1.0, rr_cv / 0.25), {'rr_cv': rr_cv}))
        else:
            concepts.append(_concept('regular_rr', 'RR 间期相对规则', 1.0 - min(1.0, rr_cv / 0.12), {'rr_cv': rr_cv}))

    intervals = prediction.get('intervals_ms') or {}
    qrs = intervals.get('qrs_duration')
    if isinstance(qrs, (int, float)) and qrs >= 120:
        concepts.append(_concept('wide_qrs', 'QRS 波群增宽', min(1.0, (qrs - 120) / 80), {'qrs_duration_ms': qrs}))
    qt = intervals.get('qt')
    if isinstance(qt, (int, float)) and qt >= 460:
        concepts.append(_concept('long_qt', 'QT 间期偏长', min(1.0, (qt - 460) / 140), {'qt_ms': qt}))

    beats = prediction.get('beats') or {}
    by_type = beats.get('by_type') or {}
    vpc_count = beats.get('vpc_count', by_type.get('vpc', 0))
    if isinstance(vpc_count, (int, float)) and vpc_count > 0:
        concepts.append(_concept('ventricular_ectopy', '室性心拍相关特征', min(1.0, vpc_count / 3), {
            'vpc_count': vpc_count,
        }))
    return concepts


def build_evidence_payload(prediction: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    return {
        'classification': {
            'label': prediction.get('label'),
            'raw_label': prediction.get('raw_label'),
            'confidence': prediction.get('confidence'),
            'task_type': prediction.get('task_type'),
            'model_version': prediction.get('model_version'),
        },
        'concepts': build_concepts(prediction, quality),
        'measurements': {
            'heart_rate': prediction.get('heart_rate'),
            'beats': prediction.get('beats'),
            'intervals_ms': prediction.get('intervals_ms'),
            'flags': prediction.get('flags', []),
        },
        'quality': quality,
        'limitations': ['单导联短时记录', '仅用于辅助分析，不替代临床诊断'],
    }
