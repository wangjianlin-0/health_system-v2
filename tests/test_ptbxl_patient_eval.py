import pytest

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
