import math

import pytest

from signal_processing.python.ecg_preprocessing import (
    ADS1292R_CODE_SCALE,
    ADS1292R_PGA_GAIN,
    ADS1292R_VREF_MV,
    parse_csv,
    process,
)
from ai_model.pipeline import analyze
from signal_processing.python.ads1292r import (
    decode_spi_frames,
    decode_status_word,
    signal_from_channels,
    signed24,
)


def test_filtered_adc_counts_convert_to_mv():
    text = (
        'timestamp(s),resp_raw,ecg_raw,resp_filtered,ecg_filtered\n'
        '0.000,0,8388608,0,0\n'
        '0.002,0,8388609,0,8388608\n'
        '0.004,0,8388610,0,-8388608\n'
    )
    result = parse_csv(text, 500)
    full_scale_mv = ADS1292R_VREF_MV / ADS1292R_PGA_GAIN
    assert result['samples'] == pytest.approx([0.0, full_scale_mv, -full_scale_mv])
    assert result['calibration']['code_scale'] == ADS1292R_CODE_SCALE
    assert result['calibration']['applied_to'] == 'ecg_filtered'
    assert result['calibration']['raw_offset_removed'] is False


def test_raw_only_multicolumn_csv_is_rejected():
    with pytest.raises(ValueError):
        parse_csv('timestamp(s),ecg_raw\n0,8388608\n0.002,8388609', 500)


def test_process_preserves_model_input():
    values = [float(index % 7) for index in range(1000)]
    result = process({'samples': values, 'sample_rate_hz': 500, 'unit': 'mV'})
    assert result['waveform'] == values
    assert result['quality']['status'] == 'basic_checks_passed'


def test_signed_24_bit_and_status_word_decode():
    assert signed24(0x7FFFFF) == 8388607
    assert signed24(0x800000) == -8388608
    assert signed24(0xFFFFFF) == -1
    status = decode_status_word(0xC20000)
    assert status['marker_valid'] is True
    assert status['ch2p_off'] is True


def test_spi_frame_maps_ch1_respiration_and_ch2_ecg():
    frame = bytes.fromhex('C00000 000064 FFFF9C')
    signal = decode_spi_frames(frame, 500)
    assert signal['respiration_samples'] == [100.0]
    assert signal['samples'][0] == pytest.approx(-100 * 2420 / (6 * 2**23))
    assert signal['hardware_status']['valid_frame_count'] == 1
    assert signal['channel_mapping'] == {'ch1': 'respiration', 'ch2': 'ecg'}


def test_csv_accepts_status_ch1_ch2_words():
    signal = parse_csv('status_word,ch1,ch2\n0xC00000,100,-100\n', 500)
    assert signal['source'] == 'ads1292r_spi_csv'
    assert signal['hardware_status']['first_status_hex'] == '0xC00000'
    assert signal['respiration_samples'] == [100.0]


def test_ecg_lead_off_blocks_ai_classification():
    rate = 500
    status = [0xC20000] * (rate * 10)
    ch1 = [round(1000 * math.sin(2 * math.pi * 0.25 * index / rate)) for index in range(rate * 10)]
    ch2 = [round(1000 * math.sin(2 * math.pi * 1.2 * index / rate)) for index in range(rate * 10)]
    result = analyze(signal_from_channels(ch1, ch2, rate, status_words=status))
    assert result['quality']['classification_eligible'] is False
    assert 'electrode_lead_off' in result['quality']['reason_codes']
    assert result['prediction']['status'] == 'skipped_quality'
