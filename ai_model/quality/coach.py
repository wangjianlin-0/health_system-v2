"""Deterministic single-lead ECG signal-quality metrics and scoring."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt, welch


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values)))) if values.size else 0.0


def _band_power(freq: np.ndarray, power: np.ndarray, low: float, high: float) -> float:
    mask = (freq >= low) & (freq < high)
    return float(np.trapezoid(power[mask], freq[mask])) if np.count_nonzero(mask) > 1 else 0.0


class QualityCoach:
    """Compute auditable research-quality indicators without medical claims."""

    def assess(self, processed: dict[str, Any], signal: dict[str, Any] | None = None) -> dict[str, Any]:
        signal = signal or {}
        values = np.asarray(processed.get('waveform_raw_mV') or processed.get('waveform') or [], dtype=float)
        rate = float(processed.get('sample_rate_hz') or 0)
        original = processed.get('quality') or {}
        reasons = list(original.get('reasons') or [])
        reason_codes: list[str] = []
        warnings: list[str] = []

        if values.size < max(1, round(rate * 2)):
            reason_codes.append('record_too_short')
        if not values.size:
            reason_codes.append('empty_signal')

        metrics = self._waveform_metrics(values, rate)
        metrics['bsqi'] = self._bsqi(values, rate)
        status_metric = self._status_metrics(signal.get('status_frames') or processed.get('status_frames'))
        metrics['status_frame'] = status_metric

        flat_fraction = metrics['flatline']['fraction']
        if flat_fraction >= 0.8:
            reason_codes.extend(['flatline', 'lead_off_suspected'])
            if '空信号或平直信号' not in reasons:
                reasons.append('空信号或平直信号')
        elif flat_fraction >= 0.2:
            warnings.append('检测到局部平直片段')

        bsqi = metrics['bsqi'].get('score')
        if metrics['motion_artifact']['level'] == 'high' and (bsqi is None or bsqi < 0.7):
            warnings.append('不同心拍检测方法一致性较低，可能存在运动或接触伪差')
        if metrics['baseline_wander']['level'] == 'high':
            warnings.append('存在较明显低频基线波动，但需结合心拍检测一致性判断影响')
        if metrics['powerline_interference']['level'] == 'high':
            warnings.append('工频干扰较强')
        if metrics['snr']['level'] == 'poor':
            warnings.append('估算信噪比较低')
        if status_metric['available'] and status_metric['abnormal_fraction'] > 0:
            warnings.append('检测到异常 ADS1292R 状态字')
        if status_metric['available'] and status_metric['abnormal_fraction'] >= 0.1:
            reason_codes.append('status_frame_abnormal')
            reasons.append('ADS1292R 状态帧异常')
        if bsqi is not None and bsqi < 0.55:
            reason_codes.append('rpeak_detection_unreliable')
            reasons.append('不同心拍检测方法结果不一致')
        elif bsqi is not None and bsqi < 0.8:
            warnings.append('部分窗口的心拍定位一致性偏低，建议复测或人工复核')

        critical = {'record_too_short', 'empty_signal', 'flatline', 'lead_off_suspected',
                    'status_frame_abnormal', 'rpeak_detection_unreliable'}
        status = 'insufficient' if critical.intersection(reason_codes) else 'basic_checks_passed'
        score = self._score(metrics, status)
        grade = ('invalid' if status == 'insufficient' else 'excellent' if score >= 90 else
                 'good' if score >= 75 else 'fair' if score >= 60 else 'poor')
        return {
            'status': status,
            'score': score,
            'grade': grade,
            'reasons': list(dict.fromkeys(reasons)),
            'reason_codes': list(dict.fromkeys(reason_codes)),
            'warnings': list(dict.fromkeys(warnings)),
            'guidance': self._guidance(metrics, status),
            'metrics': metrics,
            'scope': ('研究级单导联质量评估：长度、有限值、平直、基线漂移、50/60 Hz工频、'
                      '运动/接触伪差、导联脱落线索、可选ADS1292R状态字、估算SNR和0–100评分；'
                      '阈值未经医疗器械临床验证。'),
            'version': 'quality-coach-bsqi-v2',
        }

    def _waveform_metrics(self, values: np.ndarray, rate: float) -> dict[str, Any]:
        if values.size < 8 or rate <= 0:
            return {
                'baseline_wander': {'ratio': None, 'level': 'unknown'},
                'powerline_interference': {'frequency_hz': None, 'ratio': None, 'level': 'unknown'},
                'motion_artifact': {'outlier_fraction': None, 'level': 'unknown'},
                'flatline': {'fraction': 1.0 if values.size else 1.0, 'level': 'high'},
                'lead_off': {'suspected': True, 'evidence': ['empty_or_too_short']},
                'snr': {'db': None, 'level': 'unknown'},
            }
        centered = values - np.median(values)
        total_rms = max(_rms(centered), 1e-12)
        nyquist = rate / 2
        if nyquist > 1:
            low_sos = butter(2, min(0.5 / nyquist, 0.95), btype='lowpass', output='sos')
            baseline = sosfiltfilt(low_sos, centered)
            baseline_ratio = min(9.99, _rms(baseline) / total_rms)
        else:
            baseline_ratio = 0.0
        baseline_level = 'high' if baseline_ratio >= 0.35 else 'moderate' if baseline_ratio >= 0.18 else 'low'

        nperseg = min(values.size, max(128, round(rate * 4)))
        freq, psd = welch(centered, fs=rate, nperseg=nperseg)
        signal_power = _band_power(freq, psd, 0.5, min(40.0, nyquist))
        candidates = [hz for hz in (50.0, 60.0) if hz < nyquist]
        line_hz = max(candidates, key=lambda hz: _band_power(freq, psd, hz - 1, hz + 1), default=None)
        line_power = _band_power(freq, psd, line_hz - 1, line_hz + 1) if line_hz else 0.0
        line_ratio = line_power / max(signal_power, 1e-15)
        line_level = 'high' if line_ratio >= 0.12 else 'moderate' if line_ratio >= 0.04 else 'low'

        derivative = np.diff(values)
        median = float(np.median(derivative))
        mad = float(np.median(np.abs(derivative - median)))
        robust_scale = max(1.4826 * mad, 1e-9)
        outlier_fraction = float(np.mean(np.abs(derivative - median) > 8 * robust_scale))
        motion_level = 'high' if outlier_fraction >= 0.03 else 'moderate' if outlier_fraction >= 0.01 else 'low'

        window = max(4, round(rate / 2))
        ranges = [float(np.ptp(values[i:i + window])) for i in range(0, values.size - window + 1, window)]
        flat_fraction = float(np.mean(np.asarray(ranges) < 1e-6)) if ranges else float(np.ptp(values) < 1e-6)
        flat_level = 'high' if flat_fraction >= 0.8 else 'moderate' if flat_fraction >= 0.2 else 'low'
        saturation_fraction = float(np.mean(np.abs(centered) > 5.0))
        lead_evidence = []
        if flat_fraction >= 0.8:
            lead_evidence.append('flatline')
        if saturation_fraction >= 0.05:
            lead_evidence.append('extreme_amplitude')

        noise_power = _band_power(freq, psd, 40.0, min(nyquist, 100.0)) + _band_power(freq, psd, 0, 0.5)
        snr_db = 10 * math.log10(max(signal_power, 1e-15) / max(noise_power, 1e-15))
        snr_level = 'good' if snr_db >= 15 else 'fair' if snr_db >= 8 else 'poor'
        return {
            'baseline_wander': {'ratio': round(baseline_ratio, 4), 'level': baseline_level},
            'powerline_interference': {'frequency_hz': line_hz, 'ratio': round(line_ratio, 4), 'level': line_level},
            'motion_artifact': {'outlier_fraction': round(outlier_fraction, 4), 'level': motion_level},
            'flatline': {'fraction': round(flat_fraction, 4), 'level': flat_level},
            'lead_off': {'suspected': bool(lead_evidence), 'evidence': lead_evidence},
            'snr': {'db': round(float(snr_db), 2), 'level': snr_level},
        }

    @staticmethod
    def _detector_a(values: np.ndarray, rate: float) -> list[int]:
        upper = min(25.0, rate * 0.45)
        if values.size < max(20, int(rate * 2)) or upper <= 5:
            return []
        filtered = sosfiltfilt(butter(3, [5.0, upper], btype='bandpass', fs=rate, output='sos'), values)
        envelope = np.abs(filtered)
        median = float(np.median(envelope))
        mad = float(np.median(np.abs(envelope - median)))
        peaks, _ = find_peaks(envelope, distance=max(1, round(rate * .25)),
                              prominence=max(4 * mad, np.ptp(envelope) * .05, 1e-9))
        return [int(value) for value in peaks]

    @staticmethod
    def _detector_b(values: np.ndarray, rate: float) -> list[int]:
        upper = min(20.0, rate * 0.45)
        if values.size < max(20, int(rate * 2)) or upper <= 8:
            return []
        filtered = sosfiltfilt(butter(2, [8.0, upper], btype='bandpass', fs=rate, output='sos'), values)
        energy = np.square(np.diff(filtered, prepend=filtered[0]))
        width = max(1, round(rate * .08))
        integrated = np.convolve(energy, np.ones(width) / width, mode='same')
        threshold = float(np.median(integrated) + 3.5 * np.median(np.abs(integrated - np.median(integrated))))
        peaks, _ = find_peaks(integrated, distance=max(1, round(rate * .25)),
                              height=max(threshold, np.max(integrated) * .03, 1e-12))
        return [int(value) for value in peaks]

    @classmethod
    def _bsqi(cls, values: np.ndarray, rate: float) -> dict[str, Any]:
        if values.size < max(20, round(rate * 4)) or rate <= 0:
            return {'score': None, 'level': 'unknown', 'matched': 0, 'detector_a': 0,
                    'detector_b': 0, 'window_seconds': 10, 'windows': []}
        centered = values - np.median(values)
        window_size = max(round(rate * 10), round(rate * 4))
        tolerance = max(1, round(rate * .15))
        windows = []
        total_matched = total_a = total_b = 0
        for start in range(0, values.size, window_size):
            segment = centered[start:start + window_size]
            if segment.size < round(rate * 4):
                continue
            a = cls._detector_a(segment, rate)
            b = cls._detector_b(segment, rate)
            used: set[int] = set()
            matched = 0
            for peak in a:
                candidates = [(abs(peak - other), index) for index, other in enumerate(b) if index not in used]
                if candidates:
                    distance, index = min(candidates)
                    if distance <= tolerance:
                        used.add(index)
                        matched += 1
            denominator = len(a) + len(b)
            score = 2 * matched / denominator if denominator else 0.0
            windows.append({'start_sec': round(start / rate, 3),
                            'end_sec': round((start + segment.size) / rate, 3),
                            'score': round(score, 3), 'detector_a': len(a),
                            'detector_b': len(b), 'matched': matched})
            total_matched += matched
            total_a += len(a)
            total_b += len(b)
        denominator = total_a + total_b
        score = 2 * total_matched / denominator if denominator else 0.0
        level = 'good' if score >= .9 else 'acceptable' if score >= .7 else 'poor'
        return {'score': round(score, 3), 'level': level, 'matched': total_matched,
                'detector_a': total_a, 'detector_b': total_b,
                'window_seconds': 10, 'windows': windows}

    @staticmethod
    def _guidance(metrics: dict[str, Any], status: str) -> list[str]:
        if status == 'insufficient':
            if metrics['status_frame']['abnormal_fraction'] >= .1 or metrics['lead_off']['suspected']:
                return ['检查电极、导线和采集设备后重新测量。']
            return ['保持安静并重新贴好电极后重新测量。']
        guidance = []
        bsqi = metrics['bsqi'].get('score')
        if bsqi is not None and bsqi >= .9:
            guidance.append('两个心拍检测方法高度一致，当前信号可继续用于逐拍分类。')
        elif bsqi is not None and bsqi >= .7:
            guidance.append('心拍定位基本可用，建议结合原始波形复核一致性较低的窗口。')
        if metrics['baseline_wander']['level'] == 'high':
            guidance.append('存在低频基线波动，建议保持身体稳定并检查电极贴合。')
        if metrics['powerline_interference']['level'] == 'high':
            guidance.append('建议远离充电器、电源线和大功率电器后重新测量。')
        return guidance[:3]

    @staticmethod
    def _status_metrics(frames: Any) -> dict[str, Any]:
        if not isinstance(frames, list) or not frames:
            return {'available': False, 'count': 0, 'abnormal_count': 0, 'abnormal_fraction': 0.0}
        parsed = []
        for item in frames:
            try:
                parsed.append(int(item, 0) if isinstance(item, str) else int(item))
            except (TypeError, ValueError):
                parsed.append(-1)
        abnormal = sum(value < 0 or value > 0xFFFFFF or value >> 20 != 0xC or value & 0x1FFF for value in parsed)
        return {'available': True, 'count': len(parsed), 'abnormal_count': abnormal,
                'abnormal_fraction': round(abnormal / len(parsed), 4)}

    @staticmethod
    def _score(metrics: dict[str, Any], status: str) -> float:
        if status == 'insufficient':
            return 0.0
        deduction = 0.0
        bsqi = metrics['bsqi'].get('score')
        deduction += min(15.0, 25 * (metrics['baseline_wander']['ratio'] or 0))
        deduction += min(20.0, 100 * (metrics['powerline_interference']['ratio'] or 0))
        if bsqi is None or bsqi < .7:
            deduction += min(20.0, 400 * (metrics['motion_artifact']['outlier_fraction'] or 0))
        if bsqi is not None:
            deduction += min(40.0, max(0.0, .9 - bsqi) * 100)
        deduction += min(20.0, 25 * metrics['flatline']['fraction'])
        snr = metrics['snr']['db']
        if snr is not None and snr < 15:
            deduction += min(25.0, 15 - snr)
        deduction += min(20.0, 100 * metrics['status_frame']['abnormal_fraction'])
        return round(max(0.0, 100.0 - deduction), 1)
