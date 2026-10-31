"""ADS1292R 72-bit frame decoding and channel adaptation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


FRAME_BYTES = 9
STATUS_MARKER = 0xC
ADC_MIN = -(1 << 23)
ADC_MAX = (1 << 23) - 1
DEFAULT_VREF_MV = 2420.0
DEFAULT_ECG_GAIN = 6.0
DEFAULT_RESPIRATION_GAIN = 1.0
DEFAULT_CHANNEL_MAPPING = {'ch1': 'respiration', 'ch2': 'ecg'}


def signed24(value: int) -> int:
    """Convert a 24-bit wire value or signed integer to signed two's complement."""
    number = int(value)
    if ADC_MIN <= number <= ADC_MAX:
        return number
    if not 0 <= number <= 0xFFFFFF:
        raise ValueError('ADS1292R 通道值必须位于 24 位范围内')
    return number - (1 << 24) if number & (1 << 23) else number


def parse_numeric_word(value: Any, field: str) -> int:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f'{field} 不能为空')
        try:
            return int(text, 0)
        except ValueError:
            try:
                number = float(text)
            except ValueError as exc:
                raise ValueError(f'{field} 必须为十进制或 0x 十六进制整数') from exc
            if not number.is_integer():
                raise ValueError(f'{field} 必须为整数')
            return int(number)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} 必须为整数') from exc


def normalize_channel_mapping(mapping: Mapping[str, str] | None = None) -> dict[str, str]:
    normalized = dict(mapping or DEFAULT_CHANNEL_MAPPING)
    if set(normalized) != {'ch1', 'ch2'}:
        raise ValueError('通道映射必须同时包含 ch1 和 ch2')
    if set(normalized.values()) != {'ecg', 'respiration'}:
        raise ValueError('两路通道必须分别映射到 ecg 和 respiration')
    return normalized


def decode_status_word(value: int) -> dict[str, Any]:
    word = int(value)
    if not 0 <= word <= 0xFFFFFF:
        raise ValueError('ADS1292R 状态字必须位于 24 位范围内')
    loff = (word >> 15) & 0x1F
    return {
        'raw': word,
        'hex': f'0x{word:06X}',
        'marker': (word >> 20) & 0xF,
        'marker_valid': ((word >> 20) & 0xF) == STATUS_MARKER,
        'reserved_zero': (word & 0x1FFF) == 0,
        'gpio': (word >> 13) & 0x3,
        'rld_stat': bool(loff & 0x10),
        'ch2n_off': bool(loff & 0x08),
        'ch2p_off': bool(loff & 0x04),
        'ch1n_off': bool(loff & 0x02),
        'ch1p_off': bool(loff & 0x01),
    }


def summarize_status_words(
    status_words: Iterable[int],
    channel_mapping: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    mapping = normalize_channel_mapping(channel_mapping)
    decoded = [decode_status_word(word) for word in status_words]
    invalid = [item for item in decoded if not item['marker_valid'] or not item['reserved_zero']]
    ch1_off = sum(item['ch1p_off'] or item['ch1n_off'] for item in decoded)
    ch2_off = sum(item['ch2p_off'] or item['ch2n_off'] for item in decoded)
    channel_off = {'ch1': ch1_off, 'ch2': ch2_off}
    frame_count = len(decoded)
    return {
        'available': bool(decoded),
        'frame_count': frame_count,
        'valid_frame_count': frame_count - len(invalid),
        'invalid_frame_count': len(invalid),
        'invalid_frame_ratio': len(invalid) / frame_count if frame_count else 0.0,
        'lead_off_frame_count': sum(
            item['ch1p_off'] or item['ch1n_off'] or item['ch2p_off'] or item['ch2n_off']
            for item in decoded
        ),
        'ecg_lead_off_frame_count': channel_off[
            next(channel for channel, purpose in mapping.items() if purpose == 'ecg')
        ],
        'respiration_lead_off_frame_count': channel_off[
            next(channel for channel, purpose in mapping.items() if purpose == 'respiration')
        ],
        'rld_fault_frame_count': sum(item['rld_stat'] for item in decoded),
        'last_gpio': decoded[-1]['gpio'] if decoded else None,
        'first_status_hex': decoded[0]['hex'] if decoded else None,
        'last_status_hex': decoded[-1]['hex'] if decoded else None,
        'status_marker': '1100',
        'channel_mapping': mapping,
    }


def _counts_to_mv(counts: list[int], vref_mv: float, gain: float) -> list[float]:
    if vref_mv <= 0 or gain <= 0:
        raise ValueError('ADS1292R VREF 和 PGA 增益必须大于 0')
    scale = float(vref_mv) / (float(gain) * (1 << 23))
    return [value * scale for value in counts]


def signal_from_channels(
    ch1: Iterable[int],
    ch2: Iterable[int],
    sample_rate_hz: float,
    *,
    status_words: Iterable[int] | None = None,
    channel_mapping: Mapping[str, str] | None = None,
    vref_mv: float = DEFAULT_VREF_MV,
    ecg_gain: float = DEFAULT_ECG_GAIN,
    respiration_gain: float = DEFAULT_RESPIRATION_GAIN,
    source: str = 'ads1292r',
) -> dict[str, Any]:
    mapping = normalize_channel_mapping(channel_mapping)
    channels = {
        'ch1': [signed24(value) for value in ch1],
        'ch2': [signed24(value) for value in ch2],
    }
    if len(channels['ch1']) != len(channels['ch2']):
        raise ValueError('ADS1292R CH1 与 CH2 样本数量不一致')
    status = list(status_words or [])
    if status and len(status) != len(channels['ch1']):
        raise ValueError('ADS1292R 状态字数量必须与通道样本数量一致')
    ecg_channel = next(channel for channel, purpose in mapping.items() if purpose == 'ecg')
    respiration_channel = next(
        channel for channel, purpose in mapping.items() if purpose == 'respiration'
    )
    ecg_counts = channels[ecg_channel]
    respiration_counts = channels[respiration_channel]
    result = {
        'samples': _counts_to_mv(ecg_counts, vref_mv, ecg_gain),
        'sample_rate_hz': float(sample_rate_hz),
        'unit': 'mV',
        'lead': f'ads1292r_{ecg_channel}_single_lead',
        'source': source,
        'input_unit': 'adc_count',
        'respiration_samples': [float(value) for value in respiration_counts],
        'respiration_sample_rate_hz': float(sample_rate_hz),
        'respiration_unit': 'adc_count',
        'channel_mapping': mapping,
        'calibration': {
            'vref_mv': float(vref_mv),
            'pga_gain': float(ecg_gain),
            'code_scale': 1 << 23,
            'applied_to': ecg_channel,
            'formula': 'mV = signed_adc_count * vref_mv / (pga_gain * 2^23)',
            'wire_encoding': '24-bit two_complement',
        },
        'respiration_calibration': {
            'pga_gain': float(respiration_gain),
            'applied_to': respiration_channel,
            'unit': 'adc_count',
            'physical_scale': 'relative',
            'note': '未提供激励电流、相位与模拟前端标定，不能直接换算为欧姆',
        },
    }
    if status:
        result['hardware_status'] = summarize_status_words(status, mapping)
    return result


def decode_spi_frames(
    payload: bytes,
    sample_rate_hz: float,
    **kwargs: Any,
) -> dict[str, Any]:
    if not payload or len(payload) % FRAME_BYTES:
        raise ValueError('ADS1292R SPI 数据长度必须是 9 字节帧的整数倍')
    status_words = []
    ch1 = []
    ch2 = []
    for offset in range(0, len(payload), FRAME_BYTES):
        frame = payload[offset:offset + FRAME_BYTES]
        status_words.append(int.from_bytes(frame[0:3], 'big'))
        ch1.append(int.from_bytes(frame[3:6], 'big'))
        ch2.append(int.from_bytes(frame[6:9], 'big'))
    return signal_from_channels(
        ch1,
        ch2,
        sample_rate_hz,
        status_words=status_words,
        source='ads1292r_spi',
        **kwargs,
    )
