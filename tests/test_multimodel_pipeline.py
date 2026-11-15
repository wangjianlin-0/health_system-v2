from ai_model.analysis import beat_analysis, rhythm_analysis
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
