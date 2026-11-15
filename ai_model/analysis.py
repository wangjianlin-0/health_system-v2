"""Normalize independent model outputs into stable analysis dimensions."""

from __future__ import annotations

import os
from collections import Counter
from typing import Any


BEAT_TYPES = ('normal', 'pac', 'pvc', 'fusion', 'paced', 'unknown')
EDGE_LABELS = {
    'N': 'normal',
    'S': 'pac',
    'V': 'pvc',
    'F': 'fusion',
    'VF': 'pvc',
    'UNCLASSIFIED': 'unknown',
}


def rhythm_analysis(prediction: dict[str, Any]) -> dict[str, Any]:
    rhythm = prediction.get('rhythm') or {}
    raw_label = str(rhythm.get('label') or prediction.get('raw_label') or '').lower()
    if not raw_label:
        raw_label = {
            'normal': 'sinus',
            'atrial_fibrillation': 'afib',
        }.get(prediction.get('label'), 'unknown')
    reported_flags = {
        str(value).lower() for value in rhythm.get('conduction_flags', [])
    }
    conduction_flags = [
        value for value in ('avb', 'bbb')
        if value == raw_label or value in reported_flags
    ]
    primary = raw_label if raw_label in {
        'sinus', 'afib', 'afl', 'ventricular', 'paced'
    } else ('other' if raw_label not in {'', 'unknown'} else 'unknown')
    return {
        'status': prediction.get('status', 'unknown'),
        'primary': primary,
        'raw_label': raw_label,
        'confidence': rhythm.get('confidence', prediction.get('confidence')),
        'distribution': rhythm.get('distribution', {}),
        'conduction_flags': conduction_flags,
        'ventricular_rhythm': raw_label == 'ventricular',
        'paced_rhythm': raw_label == 'paced',
        'model_version': prediction.get('model_version'),
    }


def rate_analysis(
    prediction: dict[str, Any],
    r_peak_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    heart_rate = prediction.get('heart_rate') or (r_peak_result or {}).get('heart_rate') or {}
    bpm = heart_rate.get('bpm')
    low = float(os.environ.get('ECG_LOW_RATE_BPM', '50'))
    high = float(os.environ.get('ECG_HIGH_RATE_BPM', '100'))
    if not isinstance(bpm, (int, float)) or bpm <= 0:
        result = 'unknown'
        bpm = None
    elif bpm < low:
        result = 'low'
    elif bpm > high:
        result = 'high'
    else:
        result = 'in_range'
    return {
        'result': result,
        'average_bpm': bpm,
        'min_bpm': heart_rate.get('min_bpm'),
        'max_bpm': heart_rate.get('max_bpm'),
        'rr_mean_ms': heart_rate.get('rr_mean_ms'),
        'rr_cv': heart_rate.get('rr_cv'),
        'regularity': heart_rate.get('regularity'),
        'display_thresholds': {'low_bpm': low, 'high_bpm': high},
        'scope': '心率展示规则，不用于判断病因',
    }


def beat_analysis(
    prediction: dict[str, Any],
    aami_result: dict[str, Any] | None,
    r_peak_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (aami_result and aami_result.get('status') == 'classified'
            and aami_result.get('source') and aami_result.get('counts') is not None
            and aami_result.get('events') is not None):
        return aami_result
    if aami_result and aami_result.get('status') == 'skipped_quality':
        return {
            'status': 'skipped_quality',
            'source': 'quality_gate',
            'model_version': None,
            'fallback_reason': aami_result.get('reason'),
            'total': 0,
            'counts': {key: 0 for key in BEAT_TYPES},
            'events': [],
            'limitations': ['信号质量不足，未执行心拍分类。'],
        }
    beats = prediction.get('beats') or {}
    events = []
    mapping = {
        'sinus': 'normal',
        'normal': 'normal',
        'vpc': 'pvc',
        'pvc': 'pvc',
        'fusion': 'fusion',
        'paced': 'paced',
        'untyped': 'unknown',
        'unknown': 'unknown',
    }
    for source in beats.get('items') or []:
        raw = str(source.get('label', 'UNCLASSIFIED')).upper()
        label = EDGE_LABELS.get(raw, 'unknown') if source.get('valid', False) else 'unknown'
        events.append({
            'sample': source.get('r_sample500'),
            'time_sec': source.get('r_seconds'),
            'label': label,
            'raw_label': raw,
            'confidence': source.get('confidence'),
            'source': f"edge_{str(prediction.get('model_version') or '').split('-')[0].lower()}",
        })
    for source in beats.get('events') or []:
        raw = str(source.get('type', 'unknown')).lower()
        events.append({
            'sample': source.get('sample'),
            'time_sec': source.get('t_s', source.get('time_sec')),
            'label': mapping.get(raw, 'unknown'),
            'raw_label': raw,
            'confidence': source.get('confidence'),
            'source': 'openecg_fallback',
        })
    counts = Counter(event['label'] for event in events)
    if not events and beats.get('by_type'):
        for raw, count in beats['by_type'].items():
            counts[mapping.get(str(raw).lower(), 'unknown')] += int(count)
    if not events and not counts and r_peak_result:
        for source in r_peak_result.get('events') or []:
            events.append({
                'sample': source.get('sample'),
                'time_sec': source.get('time_sec', source.get('t_s')),
                'label': 'unknown',
                'raw_label': 'Q',
                'confidence': None,
                'source': 'r_peak_detector',
            })
        counts['unknown'] = len(events)
    total = int(beats.get('count') or sum(counts.values()))
    edge_source = str(prediction.get('model_version') or '').lower()
    source = ('edge_cnn' if edge_source.startswith('cnn') else
              'edge_hgb' if edge_source.startswith('hgb') else
              'openecg_fallback') if beats else (
        'r_peak_detector' if events else 'openecg_fallback'
    )
    return {
        'status': ('classified' if source.startswith('edge_') and events else
                   'fallback' if beats else
                   'r_peak_only' if events else 'model_unavailable'),
        'source': source,
        'model_version': prediction.get('model_version'),
        'fallback_reason': (aami_result or {}).get('reason'),
        'total': total,
        'counts': {key: int(counts.get(key, 0)) for key in BEAT_TYPES},
        'events': events,
        'limitations': [
            *(
                ['CNN/HGB 为研究用途逐拍模型，结果不构成医疗诊断。']
                if source.startswith('edge_') else
                ['当前未加载独立逐拍模型，PAC 等类别可能无法完整识别。']
            ),
            *(
                ['当前只有 R 峰位置，未对心拍形态进行分类。']
                if source == 'r_peak_detector' else []
            ),
        ],
    }


def legacy_beats(result: dict[str, Any]) -> dict[str, Any]:
    counts = result.get('counts') or {}
    return {
        'count': result.get('total', 0),
        'vpc_count': counts.get('pvc', 0),
        'by_type': {
            'normal': counts.get('normal', 0),
            'pac': counts.get('pac', 0),
            'vpc': counts.get('pvc', 0),
            'fusion': counts.get('fusion', 0),
            'paced': counts.get('paced', 0),
            'unknown': counts.get('unknown', 0),
        },
        'classified_count': sum(int(counts.get(key, 0)) for key in ('normal', 'pac', 'pvc', 'fusion', 'paced')),
        'unclassified_count': int(counts.get('unknown', 0)),
        'events': result.get('events', []),
    }
