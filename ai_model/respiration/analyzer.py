"""NeuroKit2-first respiration analysis with a deterministic local fallback."""

from __future__ import annotations

import math
import os
import statistics
from fractions import Fraction
from typing import Any


class RespirationAnalyzer:
    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or os.environ.get('ECG_RESPIRATION_PROVIDER', 'neurokit2')

    def analyze(self, processed: dict[str, Any]) -> dict[str, Any]:
        samples = processed.get('respiration_waveform') or []
        local = dict(processed.get('respiration') or {})
        if not samples:
            return {
                **local,
                'provider': 'none',
                'pause_candidates': [],
                'calibrated_ohm': False,
            }
        if self.provider in ('', 'none', 'local'):
            return self._fallback(local, 'local_rules')
        try:
            return self._neurokit(
                [float(value) for value in samples],
                float(processed.get('respiration_sample_rate_hz') or 0),
                str(processed.get('respiration_unit') or 'relative'),
                local,
            )
        except Exception as exc:
            result = self._fallback(local, 'local_fallback')
            result['fallback_reason'] = f'{type(exc).__name__}: {exc}'
            return result

    def _neurokit(
        self,
        samples: list[float],
        sample_rate_hz: float,
        unit: str,
        local: dict[str, Any],
    ) -> dict[str, Any]:
        import neurokit2 as nk
        import numpy as np
        from scipy.signal import resample_poly

        if sample_rate_hz <= 0:
            raise ValueError('呼吸采样率无效')
        target_rate = int(os.environ.get('ECG_RESPIRATION_TARGET_HZ', '25'))
        ratio = Fraction(target_rate / sample_rate_hz).limit_denominator(1000)
        values = np.asarray(samples, dtype=np.float64)
        if ratio.numerator != ratio.denominator:
            values = resample_poly(values, ratio.numerator, ratio.denominator)
        signals, info = nk.rsp_process(values, sampling_rate=target_rate)
        peaks = [int(value) for value in info.get('RSP_Peaks', [])]
        troughs = [int(value) for value in info.get('RSP_Troughs', [])]
        rate_values = []
        for value in signals.get('RSP_Rate', []):
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                rate_values.append(numeric)
        rate_bpm = round(statistics.median(rate_values), 1) if rate_values else local.get('rate_bpm')
        intervals = [(right - left) / target_rate for left, right in zip(peaks, peaks[1:])]
        interval_cv = None
        if len(intervals) >= 2 and statistics.mean(intervals) > 0:
            interval_cv = round(statistics.pstdev(intervals) / statistics.mean(intervals), 3)
        pause_candidates = self._pause_candidates(peaks, target_rate)
        status = local.get('status', 'good')
        if len(peaks) < 2:
            status = 'insufficient'
        return {
            'available': True,
            'status': status,
            'provider': 'neurokit2',
            'processing_version': 'neurokit2-rsp-v1',
            'quality_score': local.get('quality_score'),
            'rate_bpm': rate_bpm,
            'regularity': None if interval_cv is None else (
                'irregular' if interval_cv > 0.25 else 'regular'
            ),
            'interval_cv': interval_cv,
            'cycle_count': len(peaks),
            'peaks': [round(value / target_rate, 4) for value in peaks],
            'troughs': [round(value / target_rate, 4) for value in troughs],
            'pause_candidates': pause_candidates,
            'unit': unit,
            'calibrated_ohm': False,
            'scope': (
                '呼吸阻抗相对波形的工程分析；不能解释为肺容量、潮气量、'
                '绝对阻抗或睡眠呼吸暂停诊断'
            ),
            'flags': local.get('flags', []),
        }

    @staticmethod
    def _pause_candidates(peaks: list[int], sample_rate_hz: int) -> list[dict[str, Any]]:
        if len(peaks) < 2:
            return []
        intervals = [(right - left) / sample_rate_hz for left, right in zip(peaks, peaks[1:])]
        median_interval = statistics.median(intervals)
        configured = float(os.environ.get('ECG_RESP_PAUSE_CANDIDATE_SECONDS', '10'))
        threshold = max(configured, median_interval * 2.5)
        return [
            {
                'start_sec': round(left / sample_rate_hz, 3),
                'end_sec': round(right / sample_rate_hz, 3),
                'duration_sec': round(interval, 3),
                'threshold_sec': round(threshold, 3),
                'label': 'long_interval_candidate',
            }
            for left, right, interval in zip(peaks, peaks[1:], intervals)
            if interval >= threshold
        ]

    @staticmethod
    def _fallback(local: dict[str, Any], provider: str) -> dict[str, Any]:
        return {
            **local,
            'provider': provider,
            'pause_candidates': [],
            'calibrated_ohm': False,
        }
