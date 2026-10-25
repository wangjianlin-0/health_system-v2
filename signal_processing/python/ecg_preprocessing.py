"""林玄初：首版 CSV 解析与基础有效性检查；正式滤波/峰检测待实现。"""
import csv
import io
import math


ADS1292R_VREF_MV = 2420.0
ADS1292R_PGA_GAIN = 6.0
ADS1292R_CODE_SCALE = 2 ** 23


def parse_csv(text, sample_rate_hz):
    rows = list(csv.reader(io.StringIO(text)))
    values = []
    hardware_column = None
    if rows:
        header = [cell.strip().lower() for cell in rows[0]]
        if 'ecg_filtered' in header:
            hardware_column = header.index('ecg_filtered')

    for index, row in enumerate(rows):
        if not row or not row[0].strip():
            continue
        if hardware_column is not None:
            if index == 0:
                continue
            if len(row) <= hardware_column:
                raise ValueError('硬件 CSV 缺少 ecg_filtered 列值')
            try:
                filtered_adc_count = float(row[hardware_column])
            except ValueError:
                raise ValueError('硬件 CSV 的 ecg_filtered 列必须为数值')
            values.append(
                filtered_adc_count * ADS1292R_VREF_MV
                / (ADS1292R_PGA_GAIN * ADS1292R_CODE_SCALE)
            )
            continue
        if len(row) != 1:
            raise ValueError('CSV 必须为单列信号，不能把时间列当幅值')
        try:
            values.append(float(row[0]))
        except ValueError:
            if index == 0 and row[0].strip().lower() in ('value', 'sample', 'mv'):
                continue
            raise ValueError('CSV 仅支持单列数值，可含 value/sample/mv 表头')
    result = {
        'samples': values,
        'sample_rate_hz': sample_rate_hz,
        'unit': 'mV',
        'lead': 'hardware_filtered' if hardware_column is not None else 'user_single_lead',
        'source': 'hardware_csv' if hardware_column is not None else 'csv_import',
    }
    if hardware_column is not None:
        result['input_unit'] = 'adc_count'
        result['calibration'] = {
            'vref_mv': ADS1292R_VREF_MV,
            'pga_gain': ADS1292R_PGA_GAIN,
            'code_scale': ADS1292R_CODE_SCALE,
            'applied_to': 'ecg_filtered',
            'formula': 'mV = adc_count * vref_mv / (pga_gain * 2^23)',
            'raw_offset_removed': False,
        }
    return result

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
    if len(values) < rate*2:
        reasons.append('记录短于 2 秒')
    if not values or max(values)-min(values) < 0.000001:
        reasons.append('空信号或平直信号')
    return {'quality': {'status': 'insufficient' if reasons else 'basic_checks_passed', 'reasons': reasons, 'scope': '仅检查长度与平直；未验证噪声和临床可用性'}, 'waveform': values, 'sample_rate_hz': rate, 'unit': signal.get('unit', 'mV'), 'duration_sec': len(values)/rate, 'heart_rate_bpm': None, 'processing_version': 'basic-validation-v0'}
