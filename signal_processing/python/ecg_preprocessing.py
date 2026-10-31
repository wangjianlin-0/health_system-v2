"""ADS1292R 双通道解析、基础有效性检查与呼吸工程指标。"""
import csv
import io
import math
import statistics

from signal_processing.python.ads1292r import (
    DEFAULT_ECG_GAIN,
    DEFAULT_VREF_MV,
    parse_numeric_word,
    signal_from_channels,
)


ADS1292R_VREF_MV = DEFAULT_VREF_MV
ADS1292R_PGA_GAIN = DEFAULT_ECG_GAIN
ADS1292R_CODE_SCALE = 2 ** 23
MAX_SAMPLES = 200000


def _adc_count_to_mv(value: float) -> float:
    return value * ADS1292R_VREF_MV / (ADS1292R_PGA_GAIN * ADS1292R_CODE_SCALE)


def _column(header: list[str], *names: str) -> int | None:
    for name in names:
        if name in header:
            return header.index(name)
    return None


def parse_csv(text, sample_rate_hz):
    """解析单列 mV、命名双通道 CSV，或 ADS1292R 原始帧列。"""
    rows = list(csv.reader(io.StringIO(text)))
    header = [cell.strip().lower() for cell in rows[0]] if rows else []
    ch1_column = _column(header, 'ch1', 'channel1', 'channel_1')
    ch2_column = _column(header, 'ch2', 'channel2', 'channel_2')
    status_column = _column(header, 'status_word', 'status', 'ads_status')
    if ch1_column is not None or ch2_column is not None:
        if ch1_column is None or ch2_column is None:
            raise ValueError('ADS1292R 原始帧 CSV 必须同时包含 CH1 和 CH2')
        channel1 = []
        channel2 = []
        status_words = []
        for row in rows[1:]:
            if not row or not any(cell.strip() for cell in row):
                continue
            required = [ch1_column, ch2_column] + ([status_column] if status_column is not None else [])
            if len(row) <= max(required):
                raise ValueError('ADS1292R 原始帧 CSV 行字段不完整')
            channel1.append(parse_numeric_word(row[ch1_column], 'CH1'))
            channel2.append(parse_numeric_word(row[ch2_column], 'CH2'))
            if status_column is not None:
                status_words.append(parse_numeric_word(row[status_column], '状态字'))
        return signal_from_channels(
            channel1,
            channel2,
            sample_rate_hz,
            status_words=status_words,
            source='ads1292r_spi_csv',
        )

    ecg_column = _column(header, 'ecg_filtered')
    respiration_column = _column(header, 'resp_filtered')
    ecg_values = []
    respiration_values = []

    for index, row in enumerate(rows):
        if not row or not any(cell.strip() for cell in row):
            continue
        if ecg_column is not None:
            if index == 0:
                continue
            if len(row) <= ecg_column:
                raise ValueError('硬件 CSV 缺少 ecg_filtered 列值')
            try:
                ecg_values.append(_adc_count_to_mv(float(row[ecg_column])))
            except ValueError as exc:
                raise ValueError('硬件 CSV 的 ecg_filtered 列必须为数值') from exc
            if respiration_column is not None:
                if len(row) <= respiration_column:
                    raise ValueError('硬件 CSV 缺少 resp_filtered 列值')
                try:
                    respiration_values.append(float(row[respiration_column]))
                except ValueError as exc:
                    raise ValueError('硬件 CSV 的 resp_filtered 列必须为数值') from exc
            continue
        if len(row) != 1:
            raise ValueError('CSV 必须为单列信号，或包含 ecg_filtered 的 ADS1292R 双通道数据')
        try:
            ecg_values.append(float(row[0]))
        except ValueError as exc:
            if index == 0 and row[0].strip().lower() in ('value', 'sample', 'mv'):
                continue
            raise ValueError('CSV 仅支持单列数值，可含 value/sample/mv 表头') from exc

    result = {
        'samples': ecg_values,
        'sample_rate_hz': sample_rate_hz,
        'unit': 'mV',
        'lead': 'ads1292r_ecg_filtered' if ecg_column is not None else 'user_single_lead',
        'source': 'hardware_csv' if ecg_column is not None else 'csv_import',
    }
    if ecg_column is not None:
        result['input_unit'] = 'adc_count'
        result['calibration'] = {
            'vref_mv': ADS1292R_VREF_MV,
            'pga_gain': ADS1292R_PGA_GAIN,
            'code_scale': ADS1292R_CODE_SCALE,
            'applied_to': 'ecg_filtered',
            'formula': 'mV = adc_count * vref_mv / (pga_gain * 2^23)',
            'raw_offset_removed': False,
            'wire_encoding': 'signed_adc_count_after_device_filter',
        }
    if respiration_column is not None:
        if len(respiration_values) != len(ecg_values):
            raise ValueError('ECG 与呼吸通道样本数量不一致')
        result['respiration_samples'] = respiration_values
        result['respiration_sample_rate_hz'] = sample_rate_hz
        result['respiration_unit'] = 'adc_count'
        result['respiration_calibration'] = {
            'applied_to': 'resp_filtered',
            'unit': 'adc_count',
            'physical_scale': 'relative',
            'note': '未提供激励电流与模拟前端标定，不能直接换算为欧姆',
        }
    return result


def _moving_average(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return list(values)
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    half = window // 2
    output = []
    for index in range(len(values)):
        start = max(0, index - half)
        end = min(len(values), index + half + 1)
        output.append((prefix[end] - prefix[start]) / (end - start))
    return output


def _respiration_summary(values: list[float], rate: float, unit: str) -> dict:
    if not values:
        return {'available': False, 'status': 'not_provided', 'rate_bpm': None}
    duration = len(values) / rate if rate > 0 else 0.0
    centered = [value - statistics.median(values) for value in values]
    smoothed = _moving_average(centered, max(1, int(round(rate * 0.25))))
    span = max(smoothed) - min(smoothed) if smoothed else 0.0
    flags = []
    if duration < 8:
        flags.append('record_too_short')
    if span < 1e-6:
        flags.append('flat_signal')

    peaks = []
    if not flags:
        threshold = min(smoothed) + span * 0.6
        min_distance = max(1, int(round(rate * 0.8)))
        for index in range(1, len(smoothed) - 1):
            if smoothed[index - 1] < smoothed[index] >= smoothed[index + 1] and smoothed[index] >= threshold:
                if peaks and index - peaks[-1] < min_distance:
                    if smoothed[index] > smoothed[peaks[-1]]:
                        peaks[-1] = index
                else:
                    peaks.append(index)

    intervals = [(right - left) / rate for left, right in zip(peaks, peaks[1:])]
    rate_bpm = round(60.0 / statistics.median(intervals), 1) if intervals else None
    interval_cv = None
    if len(intervals) >= 2 and statistics.mean(intervals):
        interval_cv = round(statistics.pstdev(intervals) / statistics.mean(intervals), 3)
    if rate_bpm is not None and not 4 <= rate_bpm <= 60:
        flags.append('rate_out_of_engineering_range')
    if len(peaks) < 2:
        flags.append('too_few_cycles')

    score = 90.0
    if flags:
        score = 40.0 if {'flat_signal', 'record_too_short', 'too_few_cycles'} & set(flags) else 65.0
    elif interval_cv is not None and interval_cv > 0.25:
        score = 70.0
    return {
        'available': True,
        'status': 'good' if score >= 80 else ('degraded' if score >= 60 else 'insufficient'),
        'quality_score': score,
        'rate_bpm': rate_bpm,
        'regularity': None if interval_cv is None else ('irregular' if interval_cv > 0.25 else 'regular'),
        'interval_cv': interval_cv,
        'cycle_count': len(peaks),
        'duration_sec': round(duration, 3),
        'unit': unit,
        'flags': flags,
        'scope': '呼吸阻抗波形的工程估计，不构成临床呼吸诊断',
        'processing_version': 'respiration-peak-v1',
    }


def process(signal):
    values = signal.get('samples', [])
    rate = float(signal.get('sample_rate_hz', 0))
    if not math.isfinite(rate) or not 50 <= rate <= 2000:
        raise ValueError('采样率须在 50–2000 Hz 之间')
    if not isinstance(values, list) or len(values) > MAX_SAMPLES:
        raise ValueError(f'样本必须为列表，最多 {MAX_SAMPLES} 点')
    values = [float(value) for value in values]
    if not all(math.isfinite(value) for value in values):
        raise ValueError('样本含非有限值')

    respiration_values = signal.get('respiration_samples') or []
    if not isinstance(respiration_values, list) or len(respiration_values) > MAX_SAMPLES:
        raise ValueError(f'呼吸样本必须为列表，最多 {MAX_SAMPLES} 点')
    respiration_values = [float(value) for value in respiration_values]
    if not all(math.isfinite(value) for value in respiration_values):
        raise ValueError('呼吸样本含非有限值')
    if respiration_values and len(respiration_values) != len(values):
        raise ValueError('ECG 与呼吸通道样本数量不一致')

    reasons = []
    if len(values) < rate * 2:
        reasons.append('记录短于 2 秒')
    if not values or max(values) - min(values) < 0.000001:
        reasons.append('空信号或平直信号')
    respiration_rate = float(signal.get('respiration_sample_rate_hz') or rate)
    respiration_unit = signal.get('respiration_unit', 'relative')
    respiration = _respiration_summary(respiration_values, respiration_rate, respiration_unit)
    hardware_status = signal.get('hardware_status')
    if hardware_status and hardware_status.get('respiration_lead_off_frame_count'):
        respiration.update({
            'status': 'insufficient',
            'quality_score': 0.0,
            'rate_bpm': None,
            'flags': list(dict.fromkeys([*respiration.get('flags', []), 'respiration_lead_off'])),
        })
    return {
        'quality': {
            'status': 'insufficient' if reasons else 'basic_checks_passed',
            'reasons': reasons,
            'scope': '检查长度、平直与有限值；高级 ECG 质量由后续质量模块完成',
        },
        'waveform': values,
        'sample_rate_hz': rate,
        'unit': signal.get('unit', 'mV'),
        'lead': signal.get('lead'),
        'duration_sec': len(values) / rate,
        'heart_rate_bpm': None,
        'respiration_waveform': respiration_values,
        'respiration_sample_rate_hz': respiration_rate,
        'respiration_unit': respiration_unit,
        'respiration': respiration,
        'calibration': signal.get('calibration'),
        'respiration_calibration': signal.get('respiration_calibration'),
        'hardware_status': hardware_status,
        'channel_mapping': signal.get('channel_mapping'),
        'processing_version': 'ads1292r-dual-channel-v1' if respiration_values else 'basic-validation-v1',
    }
