"""Normalize single-lead uploads and ADS1292R vendor exports."""
import csv
import io
import math
import numpy as np
from scipy.signal import butter, sosfiltfilt, iirnotch, filtfilt

ADS_ZERO = 1 << 23
ADS_VREF_V = 2.42
ADS_PGA_GAIN = 6.0
ADS_LSB_MV = ADS_VREF_V * 1000.0 / (ADS_PGA_GAIN * ADS_ZERO)


def _ads_raw_to_mv(raw):
    raw = float(raw)
    if not math.isfinite(raw) or not raw.is_integer() or not 0 <= raw < 2**24:
        raise ValueError('ADC code must be an integer in [0, 16777215]')
    return (raw - ADS_ZERO) * ADS_LSB_MV


def parse_csv(text, sample_rate_hz):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError('CSV 为空')
    header = [cell.strip().lower() for cell in rows[0]]
    if 'ecg_raw' in header:
        col = header.index('ecg_raw')
        values = []
        timestamps = []
        for row in rows[1:]:
            if not row or all(not c.strip() for c in row):
                continue
            if len(row) <= col:
                raise ValueError('硬件 CSV 缺少 ecg_raw 列值')
            try:
                values.append(_ads_raw_to_mv(float(row[col])))
                if 'timestamp(s)' in header:
                    timestamps.append(float(row[header.index('timestamp(s)')]))
            except ValueError as exc:
                raise ValueError('硬件 CSV 的 ecg_raw 列必须为数值') from exc
        if timestamps:
            rate = float(sample_rate_hz)
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError('采样率必须为正数')
            if not all(math.isfinite(t) for t in timestamps) or any(
                abs((b-a)-1/rate) > max(1e-6, .01/rate)
                for a,b in zip(timestamps, timestamps[1:])
            ):
                raise ValueError('时间戳不连续或与指定采样率不匹配，不自动补点')
        return {'samples': values, 'sample_rate_hz': sample_rate_hz, 'unit': 'mV',
                'lead': 'ecg_single_lead', 'source': 'ads1292r_csv',
                'conversion': {'encoding': 'offset_binary_24', 'zero_code': ADS_ZERO,
                               'vref_v': ADS_VREF_V, 'pga_gain': ADS_PGA_GAIN,
                               'lsb_mV': ADS_LSB_MV, 'input_column': 'ecg_raw'}}
    if 'ecg_filtered' in header:
        raise ValueError('ecg_filtered 单位未知，请提供 ecg_raw 或已转换的单列 mV')
    values = []
    for index, row in enumerate(rows):
        if not row or not row[0].strip():
            continue
        if len(row) != 1:
            raise ValueError('CSV 必须为单列信号，不能把时间列当信号')
        try:
            values.append(float(row[0]))
        except ValueError:
            if index == 0 and row[0].strip().lower() in ('value', 'sample', 'mv'):
                continue
            raise ValueError('CSV 仅支持单列数值，可含 value/sample/mv 表头')
    return {'samples': values, 'sample_rate_hz': sample_rate_hz, 'unit': 'mV',
            'lead': 'user_single_lead', 'source': 'csv_import'}


def _baseline_remove(values, rate):
    # Offline rhythm-view filter, not a diagnostic/ST measurement filter.
    x = np.asarray(values, dtype=float)
    if len(x) < max(32, rate * 2):
        return values[:]
    if rate > 110:
        b, a = iirnotch(50, 30, fs=rate)
        x = filtfilt(b, a, x)
    sos = butter(2, [0.5, min(40, rate * .4)], btype='bandpass', fs=rate, output='sos')
    return sosfiltfilt(sos, x).tolist()


def process(signal):
    values = signal.get('samples', [])
    rate = float(signal.get('sample_rate_hz', 0))
    if not math.isfinite(rate) or not 50 <= rate <= 2000:
        raise ValueError('采样率须在 50–2000 Hz 之间')
    if not isinstance(values, list) or len(values) > 200000:
        raise ValueError('样本必须为列表，最多 200000 点')
    values = [float(v) for v in values]
    if not all(math.isfinite(v) for v in values):
        raise ValueError('样本含非有限值')
    reasons = []
    span = max(values) - min(values) if values else 0.0
    if len(values) < rate * 2:
        reasons.append('记录短于 2 秒')
    if not values or span < 0.000001:
        reasons.append('空信号或平直信号')
    if len(values) > 1:
        jump = max(abs(values[i] - values[i-1]) for i in range(1, len(values)))
        if jump > max(5.0, span * 0.8):
            reasons.append('存在突变或电极接触伪差')
    result = {'quality': {'status': 'insufficient' if reasons else 'basic_checks_passed',
                          'reasons': reasons,
                          'scope': '长度、有限值、平直、突变检查；另提供节律显示滤波波形；未验证临床质量'},
              'waveform': values,
              'waveform_processed_mV': _baseline_remove(values, rate) if values else [],
              'waveform_raw_mV': values, 'sample_rate_hz': rate,
              'unit': signal.get('unit', 'mV'), 'duration_sec': len(values) / rate,
              'heart_rate_bpm': None,
              'processing_version': 'ads1292r-mv-v1',
              'filter_metadata': {'profile': 'offline-rhythm-view', 'bandpass_hz': [0.5, min(40, rate*.4)], 'order': 2, 'zero_phase': True, 'notch_hz': 50 if rate > 110 else None, 'notch_q': 30, 'model_waveform': 'unfiltered_mV'}}
    for key in ('lead', 'source', 'conversion'):
        if key in signal:
            result[key] = signal[key]
    return result
