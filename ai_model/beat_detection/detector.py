"""Independent R-peak detection used before optional beat classification."""

from __future__ import annotations

import math
import os
import statistics
from typing import Any


class RPeakDetector:
    def __init__(self, provider: str | None = None) -> None:
        self.provider = (
            provider or os.environ.get('ECG_RPEAK_PROVIDER', 'neurokit2')
        ).lower()

    def detect(
        self,
        waveform: list[float],
        sample_rate_hz: float,
        openecg_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not waveform or not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
            return self._result([], sample_rate_hz, 'none', 'invalid_input')

        source = 'openecg_events'
        fallback_reason = None
        if self.provider in {'', 'none', 'openecg'}:
            peaks = self._openecg_peaks(openecg_events or [], sample_rate_hz)
        else:
            try:
                peaks = self._neurokit(waveform, sample_rate_hz)
                source = 'neurokit2'
            except Exception as exc:
                fallback_reason = f'{type(exc).__name__}: {exc}'
                try:
                    peaks = self._scipy(waveform, sample_rate_hz)
                    source = 'scipy_fallback'
                except Exception as fallback_exc:
                    fallback_reason += (
                        f'; {type(fallback_exc).__name__}: {fallback_exc}'
                    )
                    peaks = []
                    source = 'openecg_events'

        events = self._events(peaks, sample_rate_hz)
        events = self._merge_openecg(events, openecg_events or [], sample_rate_hz)
        if not events and openecg_events:
            events = self._normalize_openecg(openecg_events, sample_rate_hz)
            source = 'openecg_events'
        result = self._result(events, sample_rate_hz, source)
        if fallback_reason:
            result['fallback_reason'] = fallback_reason
        return result

    @staticmethod
    def _neurokit(waveform: list[float], sample_rate_hz: float) -> list[int]:
        import neurokit2 as nk

        sampling_rate = int(round(sample_rate_hz))
        cleaned = nk.ecg_clean(
            waveform,
            sampling_rate=sampling_rate,
            method='neurokit',
        )
        _, info = nk.ecg_peaks(
            cleaned,
            sampling_rate=sampling_rate,
            method='neurokit',
            correct_artifacts=True,
        )
        return sorted({int(value) for value in info.get('ECG_R_Peaks', [])})

    @staticmethod
    def _scipy(waveform: list[float], sample_rate_hz: float) -> list[int]:
        import numpy as np
        from scipy.signal import butter, detrend, find_peaks, sosfiltfilt

        values = detrend(np.asarray(waveform, dtype=np.float64))
        sampling_rate = float(sample_rate_hz)
        if values.size < max(10, int(sampling_rate)):
            return []
        upper = min(25.0, sampling_rate * 0.45)
        if upper <= 5.0:
            filtered = values
        else:
            sos = butter(3, [5.0, upper], btype='bandpass', fs=sampling_rate, output='sos')
            filtered = sosfiltfilt(sos, values)
        envelope = np.abs(filtered)
        median = float(np.median(envelope))
        mad = float(np.median(np.abs(envelope - median)))
        prominence = max(mad * 4.0, float(np.ptp(envelope)) * 0.05, 1e-9)
        peaks, _ = find_peaks(
            envelope,
            distance=max(1, int(round(sampling_rate * 0.25))),
            prominence=prominence,
        )
        return [int(value) for value in peaks]

    @staticmethod
    def _events(peaks: list[int], sample_rate_hz: float) -> list[dict[str, Any]]:
        return [
            {
                'sample': peak,
                't_s': round(peak / sample_rate_hz, 6),
                'time_sec': round(peak / sample_rate_hz, 6),
                'type': 'untyped',
                'source': 'independent_rpeak',
            }
            for peak in peaks
            if peak >= 0
        ]

    @staticmethod
    def _openecg_peaks(
        events: list[dict[str, Any]],
        sample_rate_hz: float,
    ) -> list[int]:
        return [
            int(round(event['time_sec'] * sample_rate_hz))
            for event in RPeakDetector._normalize_openecg(events, sample_rate_hz)
        ]

    @staticmethod
    def _normalize_openecg(
        events: list[dict[str, Any]],
        sample_rate_hz: float,
    ) -> list[dict[str, Any]]:
        normalized = []
        for event in events:
            time_value = event.get('t_s', event.get('time_sec'))
            if not isinstance(time_value, (int, float)):
                sample = event.get('sample')
                if not isinstance(sample, (int, float)):
                    continue
                time_value = float(sample) / sample_rate_hz
            sample = event.get('sample')
            if not isinstance(sample, (int, float)):
                sample = round(float(time_value) * sample_rate_hz)
            normalized.append({
                'sample': int(sample),
                't_s': round(float(time_value), 6),
                'time_sec': round(float(time_value), 6),
                'type': str(event.get('type') or 'untyped').lower(),
                'confidence': event.get('confidence'),
                'source': 'openecg',
            })
        return sorted(normalized, key=lambda item: item['time_sec'])

    @staticmethod
    def _merge_openecg(
        detected: list[dict[str, Any]],
        openecg_events: list[dict[str, Any]],
        sample_rate_hz: float,
    ) -> list[dict[str, Any]]:
        reference = RPeakDetector._normalize_openecg(openecg_events, sample_rate_hz)
        if not reference:
            return detected
        tolerance = float(os.environ.get('ECG_RPEAK_MERGE_TOLERANCE_SECONDS', '0.15'))
        used: set[int] = set()
        for event in detected:
            candidates = [
                (abs(event['time_sec'] - item['time_sec']), index, item)
                for index, item in enumerate(reference)
                if index not in used
            ]
            if not candidates:
                continue
            distance, index, match = min(candidates, key=lambda value: value[0])
            if distance <= tolerance:
                used.add(index)
                event['type'] = match['type']
                event['openecg_confidence'] = match.get('confidence')
                event['source'] = 'independent_rpeak+openecg_type'
        detected.extend(item for index, item in enumerate(reference) if index not in used)
        return sorted(detected, key=lambda item: item['time_sec'])

    @staticmethod
    def _result(
        events: list[dict[str, Any]],
        sample_rate_hz: float,
        provider: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        intervals = [
            right['time_sec'] - left['time_sec']
            for left, right in zip(events, events[1:])
            if right['time_sec'] > left['time_sec']
        ]
        bpm_values = [60.0 / interval for interval in intervals if interval > 0]
        average_bpm = round(60.0 / statistics.median(intervals), 1) if intervals else None
        rr_cv = None
        if len(intervals) >= 2 and statistics.mean(intervals) > 0:
            rr_cv = round(statistics.pstdev(intervals) / statistics.mean(intervals), 3)
        return {
            'status': 'detected' if events else 'insufficient',
            'provider': provider,
            'reason': reason,
            'count': len(events),
            'events': events,
            'heart_rate': {
                'bpm': average_bpm,
                'min_bpm': round(min(bpm_values), 1) if bpm_values else None,
                'max_bpm': round(max(bpm_values), 1) if bpm_values else None,
                'rr_mean_ms': round(statistics.mean(intervals) * 1000, 1) if intervals else None,
                'rr_cv': rr_cv,
                'regularity': None if rr_cv is None else (
                    'irregular' if rr_cv > 0.2 else 'regular'
                ),
                'source': provider,
            },
            'scope': '独立 R 峰定位和心率工程估计，不构成心律失常诊断',
        }
