"""单导联 ECG 的质量评估和复测指导。

这里的指标是工程筛查指标，不是临床诊断指标。它们用于决定是否值得
继续调用分类器，以及告诉用户下一次测量应该调整什么。
"""

from __future__ import annotations

import math
import os
import statistics
from typing import Any

from ai_model.quality.external import assess_external_quality


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _rms(values: list[float]) -> float:
    return math.sqrt(_mean([value * value for value in values]))


def _tone_ratio(values: list[float], sample_rate_hz: float, frequency: float) -> float:
    """Estimate one mains-frequency component with a Goertzel-like projection."""
    centered = [value - _mean(values) for value in values]
    total_power = sum(value * value for value in centered)
    if total_power <= 1e-12 or len(centered) < 2:
        return 0.0
    omega = 2.0 * math.pi * frequency / sample_rate_hz
    cosine = math.cos(omega)
    sine = math.sin(omega)
    real = sum(value * math.cos(omega * index) for index, value in enumerate(centered))
    imaginary = sum(value * math.sin(omega * index) for index, value in enumerate(centered))
    component_power = 2.0 * (real * real + imaginary * imaginary) / len(centered) ** 2
    return max(0.0, min(1.0, component_power / (total_power / len(centered))))


def _segment_means(values: list[float], segment_size: int) -> list[float]:
    if not values:
        return [0.0, 0.0, 0.0]
    segment_size = max(1, min(segment_size, len(values) // 3 or 1))
    return [
        _mean(values[:segment_size]),
        _mean(values[len(values) // 2 - segment_size // 2:len(values) // 2 + segment_size // 2]),
        _mean(values[-segment_size:]),
    ]


def assess_signal_quality(samples: list[float], sample_rate_hz: float) -> dict[str, Any]:
    """Return deterministic quality metrics and issue evidence for one recording."""
    values = [float(value) for value in samples]
    rate = float(sample_rate_hz)
    hard_reasons: list[str] = []
    if not values:
        hard_reasons.append('空信号')
    if len(values) < rate * 2:
        hard_reasons.append('记录短于 2 秒')
    if values and max(values) - min(values) < 0.000001:
        hard_reasons.append('空信号或平直信号')

    if hard_reasons:
        result = {
            'status': 'insufficient',
            'classification_eligible': False,
            'score': 0.0,
            'grade': 'invalid',
            'reasons': hard_reasons,
            'issues': [
                {'code': 'signal_invalid', 'label': reason, 'severity': 'high'}
                for reason in hard_reasons
            ],
            'metrics': {
                'duration_sec': len(values) / rate if rate else 0.0,
                'amplitude_range': max(values) - min(values) if values else 0.0,
            },
            'scope': '工程质量筛查，不代表临床可用性或疾病诊断',
        }
        result['reason_codes'] = [issue['code'] for issue in result['issues']]
        return result

    amplitude_range = max(values) - min(values)
    centered = [value - _mean(values) for value in values]
    signal_rms = _rms(centered)
    differences = [values[index] - values[index - 1] for index in range(1, len(values))]
    absolute_differences = [abs(value) for value in differences]
    median_difference = statistics.median(absolute_differences) if absolute_differences else 0.0
    robust_jump_limit = max(median_difference * 12.0, amplitude_range * 0.20, 1e-9)
    jump_ratio = sum(value > robust_jump_limit for value in absolute_differences) / max(1, len(absolute_differences))

    means = _segment_means(values, int(rate * 2))
    baseline_drift_ratio = (max(means) - min(means)) / max(amplitude_range, 1e-9)
    powerline_ratio = max(
        _tone_ratio(values, rate, 50.0),
        _tone_ratio(values, rate, 60.0),
    )
    derivative_rms = _rms(differences)
    snr_proxy_db = 20.0 * math.log10(max(signal_rms, 1e-9) / max(derivative_rms, 1e-9))
    flatline_ratio = sum(
        value <= max(amplitude_range * 0.001, 1e-9)
        for value in absolute_differences
    ) / max(1, len(absolute_differences))

    issues: list[dict[str, Any]] = []
    score = 100.0
    if jump_ratio > 0.08:
        score -= 25.0
        issues.append({
            'code': 'motion_artifact',
            'label': '疑似运动干扰',
            'severity': 'medium',
            'evidence': {'jump_ratio': round(jump_ratio, 4)},
        })
    if baseline_drift_ratio > 0.20:
        score -= 20.0
        issues.append({
            'code': 'baseline_drift',
            'label': '基线漂移',
            'severity': 'medium',
            'evidence': {'baseline_drift_ratio': round(baseline_drift_ratio, 4)},
        })
    if powerline_ratio > 0.12:
        score -= 20.0
        issues.append({
            'code': 'powerline_noise',
            'label': '疑似工频干扰',
            'severity': 'medium',
            'evidence': {'powerline_ratio': round(powerline_ratio, 4)},
        })
    if snr_proxy_db < 6.0:
        score -= 25.0
        issues.append({
            'code': 'low_snr',
            'label': '信噪比偏低',
            'severity': 'high',
            'evidence': {'snr_proxy_db': round(snr_proxy_db, 2)},
        })
    if flatline_ratio > 0.995:
        score -= 30.0
        issues.append({
            'code': 'contact_or_flatline',
            'label': '长段信号变化很小',
            'severity': 'high',
            'evidence': {'flatline_ratio': round(flatline_ratio, 4)},
        })

    score = round(max(0.0, min(100.0, score)), 1)
    status = 'insufficient' if score < 50.0 else 'degraded' if score < 70.0 else 'basic_checks_passed'
    result = {
        'status': status,
        'classification_eligible': score >= 50.0,
        'score': score,
        'grade': 'poor' if score < 50.0 else 'fair' if score < 70.0 else 'good',
        'reasons': [issue['label'] for issue in issues],
        'issues': issues,
        'metrics': {
            'duration_sec': round(len(values) / rate, 3),
            'amplitude_range': round(amplitude_range, 6),
            'baseline_drift_ratio': round(baseline_drift_ratio, 4),
            'powerline_noise_ratio': round(powerline_ratio, 4),
            'motion_artifact_ratio': round(jump_ratio, 4),
            'snr_proxy_db': round(snr_proxy_db, 2),
            'flatline_ratio': round(flatline_ratio, 4),
        },
        'scope': '工程质量筛查，不代表临床可用性或疾病诊断',
    }
    result['reason_codes'] = [issue['code'] for issue in issues]
    return result


def merge_external_quality(
    local_quality: dict[str, Any],
    samples: list[float],
    sample_rate_hz: float,
) -> dict[str, Any]:
    """Attach optional external evidence and apply conservative gating."""
    provider = os.environ.get('ECG_QUALITY_PROVIDER', 'none')
    external = assess_external_quality(samples, sample_rate_hz, provider)
    quality = dict(local_quality)
    quality['external_quality'] = external
    if not external.get('available'):
        return quality

    label = str(external.get('label', '')).lower()
    if label == 'unacceptable':
        issue = {
            'code': 'external_quality_unacceptable',
            'label': '外部质量评估不建议继续分析',
            'severity': 'high',
            'evidence': {
                'provider': external.get('provider'),
                'label': external.get('label'),
            },
        }
        quality['issues'] = [*quality.get('issues', []), issue]
        quality['reason_codes'] = [*quality.get('reason_codes', []), issue['code']]
        quality['reasons'] = [*quality.get('reasons', []), issue['label']]
        quality['score'] = min(float(quality.get('score', 0)), 40.0)
        quality['status'] = 'insufficient'
        quality['grade'] = 'poor'
        quality['classification_eligible'] = False
    elif label == 'barely acceptable':
        quality['score'] = min(float(quality.get('score', 0)), 70.0)
        if quality['score'] < 70:
            quality['status'] = 'degraded'
            quality['grade'] = 'fair'
    return quality


def compare_quality(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any] | None:
    if not previous:
        return None
    previous_score = previous.get('score')
    current_score = current.get('score')
    if not isinstance(previous_score, (int, float)) or not isinstance(current_score, (int, float)):
        return None
    delta = round(float(current_score) - float(previous_score), 1)
    if delta >= 5:
        trend = 'improved'
        message = '这次信号比上次更清楚。'
    elif delta <= -5:
        trend = 'declined'
        message = '这次信号比上次更差，建议按提示重新调整。'
    else:
        trend = 'unchanged'
        message = '这次信号质量与上次接近。'
    previous_codes = set(previous.get('reason_codes', []))
    current_codes = set(current.get('reason_codes', []))
    return {
        'trend': trend,
        'score_delta': delta,
        'previous_score': previous_score,
        'current_score': current_score,
        'issues_removed': sorted(previous_codes - current_codes),
        'issues_remaining': sorted(current_codes),
        'message': message,
    }


def build_measurement_coach(
    quality: dict[str, Any],
    previous_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action_map = {
        'motion_artifact': '请坐稳，把手臂放在桌面上，测量时不要说话或移动。',
        'baseline_drift': '请坐稳休息，放松手臂并给予支撑；检查电极清洁、干燥且贴合，避免拉扯导线，正常呼吸后复测。',
        'powerline_noise': '请远离充电器、插线板和其他电器后再测量。',
        'low_snr': '请清洁并擦干电极接触处，确认电极贴紧皮肤。',
        'contact_or_flatline': '请重新贴好电极，确认接触牢固且皮肤没有过多汗液。',
        'signal_invalid': '请完整记录至少 10 秒，不要在中途移动或拔掉电极。',
    }
    actions = []
    for issue in quality.get('issues', []):
        code = issue.get('code')
        if code in action_map and action_map[code] not in actions:
            actions.append(action_map[code])
    if not actions:
        actions = ['保持当前姿势，安静完成下一次记录。']
    comparison = compare_quality(previous_quality, quality)
    return {
        'status': 'retake_required' if quality.get('score', 0) < 70 else 'ready',
        'quality_score': quality.get('score', 0),
        'message': (
            '请先调整后重新测量，系统会比较前后质量。'
            if quality.get('score', 0) < 70
            else '当前信号质量达到辅助分析要求。'
        ),
        'actions': actions[:4],
        'verification': {
            'next_measurement_should': '质量评分提高且相关干扰项减少',
            'comparison': comparison,
        },
    }
