import math

from ai_model.quality.coach import QualityCoach
from signal_processing.python.ecg_preprocessing import parse_csv, process


def assessed(samples, rate=500, **extra):
    signal = {'samples': samples, 'sample_rate_hz': rate, 'unit': 'mV', **extra}
    processed = process(signal)
    return QualityCoach().assess(processed, signal)


def test_quality_coach_outputs_complete_metrics_and_score():
    samples = [0.7 * math.sin(2 * math.pi * 1.2 * i / 500) for i in range(5000)]
    quality = assessed(samples)
    assert quality['status'] == 'basic_checks_passed'
    assert 0 <= quality['score'] <= 100
    assert quality['grade'] in {'excellent', 'good', 'fair', 'poor'}
    assert set(quality['metrics']) == {
        'baseline_wander', 'powerline_interference', 'motion_artifact',
        'flatline', 'lead_off', 'snr', 'status_frame', 'bsqi',
    }


def test_flatline_is_insufficient_and_suspects_lead_off():
    quality = assessed([0.0] * 2000)
    assert quality['status'] == 'insufficient'
    assert quality['score'] == 0
    assert 'flatline' in quality['reason_codes']
    assert quality['metrics']['lead_off']['suspected'] is True


def test_project_synthetic_ecg_has_usable_bsqi_and_no_motion_warning():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / 'ai_model/vendor/ecg_edge/model/inference/examples/synthetic500.csv'
    samples = [float(value) for value in path.read_text().splitlines()]
    quality = assessed(samples)
    assert quality['metrics']['bsqi']['score'] >= 0.7
    assert not any('运动或接触伪差' in warning for warning in quality['warnings'])
    assert quality['score'] >= 65


def test_powerline_and_motion_are_quantified():
    samples = []
    for i in range(5000):
        value = 0.5 * math.sin(2 * math.pi * 1.2 * i / 500)
        value += 0.35 * math.sin(2 * math.pi * 50 * i / 500)
        if i % 250 == 0:
            value += 6
        samples.append(value)
    quality = assessed(samples)
    assert quality['metrics']['powerline_interference']['frequency_hz'] == 50.0
    assert quality['metrics']['powerline_interference']['ratio'] > 0
    assert quality['metrics']['motion_artifact']['outlier_fraction'] > 0


def test_ads_status_column_is_parsed_and_abnormal_frames_gate_quality():
    rows = ['timestamp(s),ecg_raw,ads_status']
    for i in range(1000):
        rows.append(f'{i/500:.3f},{8388608 + (i % 10)},0xC00000')
    parsed = parse_csv('\n'.join(rows), 500)
    assert len(parsed['status_frames']) == 1000
    parsed['status_frames'][0:200] = [0] * 200
    quality = QualityCoach().assess(process(parsed), parsed)
    assert quality['metrics']['status_frame']['available'] is True
    assert quality['metrics']['status_frame']['abnormal_fraction'] == 0.2
    assert quality['status'] == 'insufficient'
