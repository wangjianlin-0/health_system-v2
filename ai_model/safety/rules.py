"""Fixed triage rules; language models must not override these results."""

from __future__ import annotations

from typing import Any


URGENT_SYMPTOMS = {
    'chest_pain',
    'severe_breathlessness',
    'fainting',
    'loss_of_consciousness',
    'confusion',
    'stroke_signs',
    'rapid_deterioration',
}


def evaluate_safety(
    quality: dict[str, Any],
    beats: dict[str, Any],
    rhythm: dict[str, Any],
    rate: dict[str, Any],
    respiration: dict[str, Any],
    symptoms: list[str] | None = None,
) -> dict[str, Any]:
    urgent = sorted(URGENT_SYMPTOMS & set(symptoms or []))
    if urgent:
        return {
            'level': 'urgent_symptoms',
            'urgent': True,
            'reasons': urgent,
            'message': (
                '请不要等待设备重新分析或反复测量。建议立即联系当地急救服务'
                '或前往急诊；请勿自行驾车。'
            ),
            'source': 'fixed_rules',
        }
    if quality.get('status') == 'insufficient':
        return {
            'level': 'repeat_measurement',
            'urgent': False,
            'reasons': quality.get('reason_codes') or quality.get('reasons', []),
            'message': '信号质量不足，请检查电极和采集状态后重新测量。',
            'source': 'fixed_rules',
        }
    counts = beats.get('counts') or {}
    abnormal = any(counts.get(key, 0) > 0 for key in ('pac', 'pvc', 'fusion', 'paced'))
    abnormal = abnormal or rhythm.get('primary') not in {'sinus', 'unknown'}
    abnormal = abnormal or bool(rhythm.get('conduction_flags'))
    abnormal = abnormal or rate.get('result') in {'low', 'high'}
    abnormal = abnormal or bool(respiration.get('pause_candidates'))
    return {
        'level': 'needs_review' if abnormal else 'reference_only',
        'urgent': False,
        'reasons': [],
        'message': (
            '建议保存记录并结合症状咨询专业人员。'
            if abnormal else
            '本次结果可作为参考；如有不适仍应咨询专业人员。'
        ),
        'source': 'fixed_rules',
    }
