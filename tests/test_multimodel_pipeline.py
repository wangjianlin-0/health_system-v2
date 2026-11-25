from ai_model.analysis import beat_analysis, rate_analysis, rhythm_analysis
from ai_model import pipeline
from ai_model.respiration.analyzer import RespirationAnalyzer
from ai_model.safety.rules import evaluate_safety


def test_cnn_items_normalize_to_standard_beat_analysis():
    prediction = {
        'status': 'classified',
        'model_version': 'CNN-H27-fold0',
        'beats': {
            'count': 3,
            'items': [
                {'r_sample500': 500, 'r_seconds': 1.0, 'valid': True, 'label': 'N', 'confidence': 0.9},
                {'r_sample500': 900, 'r_seconds': 1.8, 'valid': True, 'label': 'S', 'confidence': 0.8},
                {'r_sample500': 1300, 'r_seconds': 2.6, 'valid': False, 'label': 'UNCLASSIFIED', 'confidence': None},
            ],
        },
    }

    result = beat_analysis(prediction, prediction)

    assert result['status'] == 'classified'
    assert result['source'] == 'edge_cnn'
    assert result['counts']['normal'] == 1
    assert result['counts']['pac'] == 1
    assert result['counts']['unknown'] == 1
    assert result['events'][1]['sample'] == 900


def test_hgb_vf_maps_to_ventricular_group_not_fibrillation():
    prediction = {
        'status': 'classified',
        'model_version': 'HGB-v92-fold0',
        'beats': {
            'count': 1,
            'items': [
                {'r_sample500': 500, 'r_seconds': 1.0, 'valid': True, 'label': 'VF', 'confidence': 0.85},
            ],
        },
    }

    result = beat_analysis(prediction, prediction)

    assert result['source'] == 'edge_hgb'
    assert result['counts']['pvc'] == 1
    assert result['counts']['fusion'] == 0


def test_openecg_remains_record_level_rhythm_source():
    result = rhythm_analysis({
        'status': 'classified',
        'model_version': 'openecg-codec-v6',
        'rhythm': {'label': 'afib', 'confidence': 0.91},
    })

    assert result['primary'] == 'afib'
    assert result['confidence'] == 0.91


def test_model_heart_rate_keeps_rr_statistics_from_detected_peaks():
    result = rate_analysis(
        {'heart_rate': {'bpm': 74.17, 'min_bpm': 61.73, 'max_bpm': 95.54}},
        {'heart_rate': {'bpm': 74.2, 'min_bpm': 61.7, 'max_bpm': 95.5,
                        'rr_mean_ms': 803.8, 'rr_cv': 0.127, 'regularity': 'regular'}},
    )

    assert result['average_bpm'] == 74.17
    assert result['min_bpm'] == 61.73
    assert result['max_bpm'] == 95.54
    assert result['rr_mean_ms'] == 803.8
    assert result['rr_cv'] == 0.127
    assert result['regularity'] == 'regular'


def test_openecg_selection_exposes_rhythm_classification_at_top_level(monkeypatch):
    monkeypatch.setattr(pipeline, 'process', lambda signal: {
        'waveform': [0.1] * 5000, 'sample_rate_hz': 500, 'unit': 'mV',
    })
    monkeypatch.setattr(pipeline._QUALITY_COACH, 'assess', lambda *_: {
        'status': 'basic_checks_passed', 'score': 90, 'reason_codes': [],
    })
    monkeypatch.setattr(pipeline, '_rhythm_prediction', lambda processed: {
        'status': 'classified', 'label': 'normal', 'confidence': 0.9,
        'model_version': 'openecg-codec-v6',
        'rhythm': {'label': 'sinus', 'confidence': 0.9},
        'heart_rate': {'bpm': 70.0},
        'beats': {
            'events': [
                {'sample': 900, 't_s': 1.8},
                {'sample': 100, 't_s': 0.2},
                {'sample': 500, 't_s': 1.0},
            ],
        },
    })
    monkeypatch.setattr(pipeline._RESPIRATION_ANALYZER, 'analyze', lambda _: {
        'provider': 'none', 'rate_bpm': None, 'cycle_count': 0, 'pause_candidates': [],
    })
    monkeypatch.setattr(pipeline, 'generate_explanation', lambda _: {'summary': '节律分析完成'})

    result = pipeline.analyze({'model_type': 'openecg'})

    assert result['prediction']['status'] == 'classified'
    assert result['prediction']['label'] == 'normal'
    assert result['prediction']['rhythm_model']['status'] == 'classified'
    assert result['prediction']['beat_model']['requested'] == 'none'
    assert result['prediction']['explanation'] == '节律分析完成'
    assert result['beat_analysis']['source'] == 'openecg_fallback'
    assert result['rate_analysis']['average_bpm'] == 70.0
    assert result['rate_analysis']['rr_mean_ms'] == 800.0
    assert result['rate_analysis']['regularity'] == 'regular'


def test_respiration_without_channel_is_explicitly_unavailable():
    result = RespirationAnalyzer().analyze({})

    assert result['provider'] == 'none'
    assert result['pause_candidates'] == []


def test_safety_uses_combined_model_dimensions():
    result = evaluate_safety(
        quality={'status': 'basic_checks_passed'},
        beats={'counts': {'pvc': 1}},
        rhythm={'primary': 'sinus', 'conduction_flags': []},
        rate={'result': 'in_range'},
        respiration={'pause_candidates': []},
    )

    assert result['level'] == 'needs_review'
