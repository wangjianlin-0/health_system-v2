import math

import ai_model.pipeline as pipeline
from ai_model.pipeline import analyze
from ai_model.quality.coach import assess_signal_quality, build_measurement_coach


def test_quality_coach_detects_powerline_noise():
    sample_rate = 500
    samples = [
        0.01 * index / sample_rate
        + 0.2 * __import__('math').sin(2 * __import__('math').pi * 50 * index / sample_rate)
        for index in range(sample_rate * 10)
    ]
    quality = assess_signal_quality(samples, sample_rate)
    assert quality['score'] < 100
    assert any(issue['code'] == 'powerline_noise' for issue in quality['issues'])
    assert quality['classification_eligible'] is True


def test_quality_coach_compares_adjustment_effect():
    previous = {'score': 45}
    current = {'score': 78, 'issues': []}
    coach = build_measurement_coach(current, previous)
    assert coach['verification']['comparison']['trend'] == 'improved'
    assert coach['verification']['comparison']['score_delta'] == 33


def test_pipeline_exposes_three_state_decision_for_short_signal():
    result = analyze({
        'samples': [0.1] * 100,
        'sample_rate_hz': 500,
        'unit': 'mV',
        'lead': 'user_single_lead',
        'source': 'test',
    })
    assert result['prediction']['decision']['state'] == 'signal_invalid'
    assert result['measurement_coach']['status'] == 'retake_required'


def test_pipeline_marks_missing_model_as_uncertain():
    samples = [
        math.sin(2 * math.pi * 1.2 * index / 500)
        for index in range(5000)
    ]
    result = analyze({
        'samples': samples,
        'sample_rate_hz': 500,
        'unit': 'mV',
        'lead': 'user_single_lead',
        'source': 'test',
    })
    assert result['prediction']['status'] == 'model_unavailable'
    assert result['prediction']['decision']['state'] == 'model_uncertain'


def test_pipeline_allows_only_qualified_assistive_classification(monkeypatch):
    monkeypatch.setattr(pipeline, 'classify', lambda processed: {
        'status': 'classified',
        'label': 'normal',
        'confidence': 0.91,
        'model_version': 'test-model',
        'explanation': None,
    })
    samples = [
        math.sin(2 * math.pi * 1.2 * index / 500)
        for index in range(5000)
    ]
    result = analyze({
        'samples': samples,
        'sample_rate_hz': 500,
        'unit': 'mV',
        'lead': 'user_single_lead',
        'source': 'test',
    })
    assert result['prediction']['decision']['state'] == 'assistive_classification'
    assert result['prediction']['decision']['can_present_classification'] is True
