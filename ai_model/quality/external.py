"""Optional external ECG quality evidence providers."""

from __future__ import annotations

from typing import Any


def _quality_score(label: str) -> float | None:
    return {
        'excellent': 100.0,
        'barely acceptable': 70.0,
        'unacceptable': 30.0,
    }.get(label.lower())


def assess_neurokit2(samples: list[float], sample_rate_hz: float) -> dict[str, Any]:
    """Run NeuroKit2 quality assessment when the optional dependency is available."""
    try:
        import neurokit2 as nk
    except ImportError:
        return {
            'available': False,
            'provider': 'neurokit2',
            'status': 'not_installed',
            'reason': '未安装 neurokit2，继续使用本地质量规则',
        }

    try:
        rate = int(round(sample_rate_hz))
        cleaned = nk.ecg_clean(samples, sampling_rate=rate)
        label = str(nk.ecg_quality(cleaned, sampling_rate=rate, method='zhao2018'))
        qrs_quality = nk.ecg_quality(
            cleaned,
            sampling_rate=rate,
            method='averageQRS',
        )
        qrs_values = [float(value) for value in qrs_quality]
        mean_qrs_quality = sum(qrs_values) / len(qrs_values) if qrs_values else None
        return {
            'available': True,
            'provider': 'neurokit2',
            'method': 'zhao2018+averageQRS',
            'status': label.lower(),
            'label': label,
            'score': _quality_score(label),
            'qrs_quality': round(mean_qrs_quality, 4)
            if mean_qrs_quality is not None
            else None,
        }
    except Exception as exc:
        return {
            'available': False,
            'provider': 'neurokit2',
            'status': 'error',
            'reason': f'{type(exc).__name__}: {exc}',
        }


def assess_ecgassess(
    samples: list[float],
    sample_rate_hz: float,
) -> dict[str, Any]:
    """Report ECGAssess as an explicit external adapter placeholder."""
    del samples, sample_rate_hz
    return {
        'available': False,
        'provider': 'ecgassess',
        'status': 'external_adapter_required',
        'reason': (
            'ECGAssess 需要外部程序适配；当前输入是 ADS1292R 单导联，'
            '流水线不自动伪造其结果'
        ),
    }


def assess_external_quality(
    samples: list[float],
    sample_rate_hz: float,
    provider: str = 'none',
) -> dict[str, Any]:
    if provider == 'ecgassess':
        return assess_ecgassess(samples, sample_rate_hz)
    if provider in ('', 'none', 'local'):
        return {
            'available': False,
            'provider': 'none',
            'status': 'disabled',
        }
    return assess_neurokit2(samples, sample_rate_hz)
