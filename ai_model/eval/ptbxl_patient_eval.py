"""Evaluate OpenECG against a frozen, patient-disjoint PTB-XL fold split.

This is an engineering evaluation utility, not a clinical validation protocol.
It requires the user to download PTB-XL and its WFDB files separately.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from ai_model.inference.openecg_adapter import OpenEcgClassifier
from ai_model.quality.coach import assess_signal_quality


TASK_LABELS = ('normal', 'atrial_fibrillation', 'other_abnormality')
ABSTAIN = 'abstain'
MODEL_VERSION_FALLBACK = 'openecg-codec-v6'
LABEL_MAPPING_VERSION = 'ptbxl-scp-record-level-v1'


def _parse_codes(value: str) -> dict[str, float]:
    parsed = ast.literal_eval(value)
    if not isinstance(parsed, dict):
        raise ValueError('scp_codes must be a dictionary')
    return {str(code).upper(): float(weight) for code, weight in parsed.items()}


def map_ptbxl_label(scp_codes: dict[str, float]) -> str | None:
    """Map conservative PTB-XL record labels to the OpenECG task labels.

    NORM is accepted as normal only when no competing diagnostic superclass or
    arrhythmia label is present. AFIB is accepted as a distinct class only when
    PTB-XL explicitly includes AFIB. Other diagnosed records map to the broad
    other_abnormality bucket. Records without a supported diagnosis are omitted.
    """
    codes = {
        str(code).upper()
        for code, likelihood in scp_codes.items()
        if isinstance(likelihood, (int, float)) and likelihood > 0
    }
    rhythms = codes & {'AFIB', 'AFL', 'SVTA', 'SARRH', 'SBRAD', 'SR'}
    if 'AFIB' in codes:
        if codes - {'AFIB'}:
            return 'other_abnormality'
        return 'atrial_fibrillation'
    if codes == {'NORM'}:
        return 'normal'
    if codes - {'NORM'}:
        return 'other_abnormality'
    return None


def patient_fold_manifest(metadata_path: Path) -> list[dict[str, Any]]:
    with metadata_path.open('r', encoding='utf-8-sig', newline='') as file:
        rows = list(csv.DictReader(file))
    required = {'ecg_id', 'patient_id', 'strat_fold', 'scp_codes', 'filename_hr'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f'PTB-XL metadata must contain columns: {sorted(required)}')

    patient_folds: dict[str, set[int]] = {}
    manifest = []
    for row in rows:
        patient_id = str(row['patient_id']).strip()
        fold = int(row['strat_fold'])
        if not patient_id:
            raise ValueError(f"Missing patient_id for ecg_id={row['ecg_id']}")
        patient_folds.setdefault(patient_id, set()).add(fold)
        true_label = map_ptbxl_label(_parse_codes(row['scp_codes']))
        manifest.append({
            'record_id': str(row['ecg_id']),
            'patient_id': patient_id,
            'fold': fold,
            'split': 'test' if fold in (9, 10) else 'development',
            'true_label': true_label,
            'record_path': row['filename_hr'],
            'sample_rate_hz': 500,
            'lead': 'II',
            'label_mapping_version': LABEL_MAPPING_VERSION,
        })
    leaked = {patient: sorted(folds) for patient, folds in patient_folds.items() if len(folds) > 1}
    if leaked:
        raise ValueError(f'Patient leakage across PTB-XL folds: {list(leaked.items())[:5]}')
    return manifest


def _safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate_predictions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError('No labeled test records were evaluated')
    labels = [*TASK_LABELS, ABSTAIN]
    matrix = {truth: {prediction: 0 for prediction in labels} for truth in TASK_LABELS}
    for row in rows:
        truth = row['true_label']
        predicted = row.get('evaluated_label', ABSTAIN)
        if truth not in TASK_LABELS or predicted not in labels:
            raise ValueError(f'Unexpected evaluation label: {truth!r} -> {predicted!r}')
        matrix[truth][predicted] += 1

    per_class = {}
    for label in TASK_LABELS:
        tp = matrix[label][label]
        fn = sum(matrix[label].values()) - tp
        fp = sum(matrix[other][label] for other in TASK_LABELS if other != label)
        tn = len(rows) - tp - fn - fp
        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        specificity = _safe_divide(tn, tn + fp)
        f1 = _safe_divide(2 * precision * recall, precision + recall)
        per_class[label] = {
            'support': sum(matrix[label].values()),
            'true_positive': tp,
            'false_negative_including_abstentions': fn,
            'false_positive': fp,
            'true_negative': tn,
            'precision': precision,
            'recall': recall,
            'sensitivity': recall,
            'specificity': specificity,
            'f1': f1,
        }

    correct = sum(matrix[label][label] for label in TASK_LABELS)
    classified = sum(
        1 for row in rows if row.get('evaluated_label') in TASK_LABELS
    )
    macro_f1 = sum(per_class[label]['f1'] for label in TASK_LABELS) / len(TASK_LABELS)
    return {
        'samples': len(rows),
        'correct': correct,
        'accuracy_including_abstentions_as_incorrect': _safe_divide(correct, len(rows)),
        'macro_f1_including_abstentions_as_missed': macro_f1,
        'coverage': _safe_divide(classified, len(rows)),
        'abstentions': len(rows) - classified,
        'per_class': per_class,
        'confusion_matrix': matrix,
        'status': 'computed_from_supplied_predictions',
    }


def _load_ptbxl_record(record_path: Path, lead: str) -> list[float]:
    try:
        import wfdb
    except ImportError as exc:
        raise RuntimeError('Install WFDB with: python -m pip install wfdb') from exc
    record = wfdb.rdrecord(str(record_path))
    signal_names = [name.strip() for name in record.sig_name]
    if lead not in signal_names:
        raise ValueError(f'Record {record_path} has no {lead} lead; available={signal_names}')
    if int(round(record.fs)) != 500:
        raise ValueError(f'Record {record_path} is {record.fs} Hz; expected the 500 Hz PTB-XL version')
    return [float(value) for value in record.p_signal[:, signal_names.index(lead)]]


def run_evaluation(
    metadata_path: Path,
    records_root: Path,
    output_dir: Path,
    folds: set[int],
    lead: str = 'II',
    confidence_threshold: float = 0.55,
    quality_threshold: float = 70.0,
    record_ids: set[str] | None = None,
) -> dict[str, Any]:
    manifest = patient_fold_manifest(metadata_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / 'ptbxl_patient_fold_manifest.csv'
    with manifest_path.open('w', encoding='utf-8-sig', newline='') as file:
        fields = [
            'record_id', 'patient_id', 'fold', 'split', 'true_label',
            'record_path', 'sample_rate_hz', 'lead', 'label_mapping_version',
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in fields} for row in manifest)
    selected = [
        row for row in manifest
        if row['fold'] in folds and row['true_label'] is not None
        and (record_ids is None or row['record_id'] in record_ids)
    ]
    if not selected:
        raise ValueError('No supported labeled records found in selected folds')
    if record_ids is not None:
        found_ids = {row['record_id'] for row in selected}
        missing_ids = record_ids - found_ids
        if missing_ids:
            raise ValueError(
                'Requested records are not labeled in the selected folds: '
                + ', '.join(sorted(missing_ids))
            )
    model = OpenEcgClassifier()
    predictions = []
    for item in selected:
        output: dict[str, Any] = {
            **item,
            'lead': lead,
            'model_version': getattr(model, 'model_version', MODEL_VERSION_FALLBACK),
            'predicted_label': None,
            'raw_label': None,
            'confidence': None,
            'quality_score': None,
            'decision_state': None,
            'failure_reason': None,
        }
        try:
            waveform = _load_ptbxl_record(records_root / item['record_path'], lead)
            quality = assess_signal_quality(waveform, 500)
            output['quality_score'] = quality.get('score')
            if not quality.get('classification_eligible') or quality.get('score', 0) < quality_threshold:
                output.update({
                    'evaluated_label': ABSTAIN,
                    'decision_state': 'signal_invalid' if not quality.get('classification_eligible') else 'model_uncertain',
                    'failure_reason': 'quality_gate: ' + ','.join(quality.get('reason_codes', [])),
                })
            else:
                prediction = model.predict({
                    'waveform': waveform,
                    'sample_rate_hz': 500,
                    'unit': 'mV',
                })
                output.update({
                    'predicted_label': prediction.get('label'),
                    'raw_label': prediction.get('raw_label'),
                    'confidence': prediction.get('confidence'),
                    'model_version': prediction.get('model_version') or output['model_version'],
                    'decision_state': 'classified' if prediction.get('status') == 'classified' else prediction.get('status'),
                })
                confidence = prediction.get('confidence')
                label = prediction.get('label')
                if prediction.get('status') != 'classified' or label not in TASK_LABELS:
                    output['evaluated_label'] = ABSTAIN
                    output['failure_reason'] = prediction.get('explanation') or 'classifier_did_not_return_supported_label'
                elif isinstance(confidence, (int, float)) and (not math.isfinite(confidence) or confidence < confidence_threshold):
                    output['evaluated_label'] = ABSTAIN
                    output['decision_state'] = 'model_uncertain'
                    output['failure_reason'] = 'confidence_below_configured_threshold'
                else:
                    output['evaluated_label'] = label
        except Exception as exc:
            output.update({
                'evaluated_label': ABSTAIN,
                'decision_state': 'evaluation_error',
                'failure_reason': f'{type(exc).__name__}: {exc}',
            })
        predictions.append(output)

    report = {
        'report_date': date.today().isoformat(),
        'dataset': 'PhysioNet PTB-XL v1.0.3, 500 Hz records',
        'task': 'record-level rhythm screening; not beat classification or clinical validation',
        'split': {
            'development_folds': sorted(set(range(1, 11)) - folds),
            'test_folds': sorted(folds),
            'patient_disjoint_check': 'passed_for_official_strat_fold_metadata',
            'test_records_selected': len(selected),
            'test_patients_selected': len({row['patient_id'] for row in selected}),
            'record_id_subset': sorted(record_ids) if record_ids is not None else None,
        },
        'lead': lead,
        'sample_rate_hz': 500,
        'unit': 'mV',
        'preprocessing': 'PTB-XL 500 Hz WFDB physical signal; lead extraction only; no extra filtering; first 10 s consumed by OpenECG',
        'label_mapping_version': LABEL_MAPPING_VERSION,
        'confidence_threshold': confidence_threshold,
        'quality_threshold': quality_threshold,
        'quality_gate': 'project local engineering score; not a medical standard',
        'metrics': evaluate_predictions(predictions),
        'label_mapping_counts': {
            label: sum(1 for row in manifest if row['true_label'] == label)
            for label in TASK_LABELS
        },
        'limitations': [
            'PTB-XL diagnostic labels are not identical to OpenECG rhythm labels; label mapping is conservative and requires domain review.',
            'Project quality score and confidence threshold are engineering gates, not clinically calibrated thresholds.',
            'Metrics are meaningful only after downloading the official dataset and successfully evaluating the selected patient-disjoint folds.',
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'ptbxl_predictions.json').write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    (output_dir / 'ptbxl_metrics.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    with (output_dir / 'ptbxl_errors.csv').open('w', encoding='utf-8-sig', newline='') as file:
        fields = [
            'record_id', 'patient_id', 'fold', 'true_label', 'predicted_label',
            'evaluated_label', 'confidence', 'quality_score', 'decision_state',
            'failure_reason', 'model_version',
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {key: row.get(key) for key in fields}
            for row in predictions
            if row.get('evaluated_label') != row.get('true_label')
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True, help='Path to ptbxl_database.csv')
    parser.add_argument('--records-root', type=Path, help='PTB-XL root containing records500/; required unless --manifest-only')
    parser.add_argument('--output-dir', type=Path, default=Path('runtime/ptbxl_eval'))
    parser.add_argument('--folds', default='9,10', help='Frozen official test folds, default: 9,10')
    parser.add_argument('--lead', default='II')
    parser.add_argument('--confidence-threshold', type=float, default=0.55)
    parser.add_argument('--quality-threshold', type=float, default=70.0)
    parser.add_argument('--record-ids', help='Optional comma-separated ECG IDs for a smoke-test subset')
    parser.add_argument('--manifest-only', action='store_true', help='Export patient-disjoint labeled manifest without model inference')
    args = parser.parse_args()
    folds = {int(part.strip()) for part in args.folds.split(',') if part.strip()}
    if not folds or not folds.issubset(set(range(1, 11))):
        parser.error('--folds must be comma-separated PTB-XL folds from 1 to 10')
    if not 0.0 <= args.confidence_threshold <= 1.0:
        parser.error('--confidence-threshold must be between 0 and 1')
    if not 0.0 <= args.quality_threshold <= 100.0:
        parser.error('--quality-threshold must be between 0 and 100')
    if args.manifest_only:
        manifest = patient_fold_manifest(args.metadata)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        target = args.output_dir / 'ptbxl_patient_fold_manifest.csv'
        fields = ['record_id', 'patient_id', 'fold', 'split', 'true_label', 'record_path', 'sample_rate_hz', 'lead', 'label_mapping_version']
        with target.open('w', encoding='utf-8-sig', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows({key: row.get(key) for key in fields} for row in manifest)
        print(f'Patient-level manifest: {target.resolve()}')
        print(f"Labeled rows: {sum(row['true_label'] is not None for row in manifest)} / {len(manifest)}")
        return
    if not args.records_root:
        parser.error('--records-root is required unless --manifest-only is set')
    report = run_evaluation(
        args.metadata,
        args.records_root,
        args.output_dir,
        folds,
        args.lead,
        args.confidence_threshold,
        args.quality_threshold,
        {part.strip() for part in args.record_ids.split(',') if part.strip()}
        if args.record_ids
        else None,
    )
    print(json.dumps(report['metrics'], ensure_ascii=False, indent=2))
    print(f"Full report: {args.output_dir.resolve() / 'ptbxl_metrics.json'}")


if __name__ == '__main__':
    main()
