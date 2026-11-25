import pytest
import ai_model.eval.ptbxl_patient_eval as evaluation

from ai_model.eval.ptbxl_patient_eval import (
    build_error_analysis,
    evaluate_predictions,
    map_ptbxl_label,
    sample_patient_disjoint_fold,
)


def test_ptbxl_rhythm_mapping_excludes_task_mismatch():
    assert map_ptbxl_label({'NORM': 100}) == 'normal'
    assert map_ptbxl_label({'NORM': 100, 'SR': 0}) == 'normal'
    assert map_ptbxl_label({'NORM': 80, 'SR': 0}) == 'normal'
    assert map_ptbxl_label({'NORM': 0, 'SR': 0}) is None
    assert map_ptbxl_label({'SR': 0}) is None
    assert map_ptbxl_label({'NORM': 100, 'SR': 0, 'ABQRS': 0}) is None
    assert map_ptbxl_label({'AFIB': 0}) == 'atrial_fibrillation'
    assert map_ptbxl_label({'PVC': 100}) == 'other_abnormality'
    assert map_ptbxl_label({'AFIB': 100, 'NORM': 100}) is None
    assert map_ptbxl_label({'MI': 100}) is None
    assert map_ptbxl_label({'XYZ': 100}) is None
    assert map_ptbxl_label({'AFIB': 0, 'MI': 100}) == 'atrial_fibrillation'
    assert map_ptbxl_label({'STACH': 0, 'STTC': 100}) == 'other_abnormality'
    assert map_ptbxl_label({'STTC': 100}) is None


def test_metrics_count_abstentions_as_missed_and_report_coverage():
    report = evaluate_predictions([
        {'true_label': 'normal', 'evaluated_label': 'normal'},
        {'true_label': 'normal', 'evaluated_label': 'abstain'},
        {'true_label': 'atrial_fibrillation', 'evaluated_label': 'other_abnormality'},
    ])
    assert report['samples'] == 3
    assert report['correct'] == 1
    assert report['abstentions'] == 1
    assert report['coverage'] == pytest.approx(2 / 3)
    assert report['per_class']['normal']['recall'] == pytest.approx(0.5)


def test_error_analysis_separates_abnormal_misses_from_rejections():
    rows = [
        {
            'true_label': 'other_abnormality',
            'evaluated_label': 'normal',
            'decision_state': 'classified',
        },
        {
            'true_label': 'atrial_fibrillation',
            'evaluated_label': 'abstain',
            'decision_state': 'model_uncertain',
            'failure_reason': 'confidence_below_configured_threshold',
        },
    ]
    analysis = build_error_analysis(rows)
    assert analysis['abnormal_missed_as_normal'] == 1
    assert analysis['abnormal_miss_rate'] == pytest.approx(0.5)
    assert analysis['error_category_counts']['confidence_rejection'] == 1


def test_sample_fold_uses_unique_patients_and_balances_classes():
    rows = []
    for label in ('normal', 'atrial_fibrillation', 'other_abnormality'):
        for index in range(3):
            rows.append({
                'record_id': f'{label}-{index}',
                'patient_id': f'{label}-patient-{index}',
                'fold': 9,
                'true_label': label,
            })
    rows.append({
        'record_id': 'normal-extra',
        'patient_id': 'normal-patient-0',
        'fold': 9,
        'true_label': 'normal',
    })
    sampled = sample_patient_disjoint_fold(rows, 9, 2, 7)
    assert len(sampled) == 6
    assert len({row['patient_id'] for row in sampled}) == 6
    assert {row['true_label'] for row in sampled} == {
        'normal', 'atrial_fibrillation', 'other_abnormality',
    }


@pytest.mark.parametrize('status,score,gate,expected', [
    ('basic_checks_passed', 85, 'hard', 'normal'),
    ('basic_checks_passed', 60, 'hard', 'normal'),
    ('basic_checks_passed', 60, 'score', 'abstain'),
    ('insufficient', 85, 'hard', 'abstain'),
])
def test_evaluation_uses_current_quality_gate(tmp_path, monkeypatch, status, score, gate, expected):
    import json
    monkeypatch.setattr(evaluation, 'patient_fold_manifest', lambda _: [{
        'record_id': '1', 'patient_id': 'p1', 'fold': 10,
        'true_label': 'normal', 'record_path': 'records500/example',
    }])
    monkeypatch.setattr(evaluation, '_load_ptbxl_record', lambda *_: [0.1] * 5000)
    monkeypatch.setattr(evaluation.QualityCoach, 'assess', lambda self, processed: {
        'status': status, 'score': score, 'reason_codes': [], 'version': 'test-quality',
    })

    class Model:
        def predict(self, processed):
            assert expected == 'normal', 'Rejected signals must not reach the model'
            return {'status': 'classified', 'label': 'normal', 'confidence': 0.9}

    monkeypatch.setattr(evaluation, 'OpenEcgClassifier', Model)
    evaluation.run_evaluation(
        tmp_path / 'metadata.csv', tmp_path, tmp_path / 'report', {10},
        quality_gate_mode=gate,
    )
    rows = json.loads((tmp_path / 'report' / 'ptbxl_predictions.json').read_text(encoding='utf-8'))
    assert rows[0]['evaluated_label'] == expected
    assert rows[0]['quality_version'] == 'test-quality'
    assert rows[0]['decision_state'] != 'evaluation_error'
    if gate == 'score' and expected == 'abstain':
        assert rows[0]['failure_reason'] == 'quality_gate: score_60_below_70'
