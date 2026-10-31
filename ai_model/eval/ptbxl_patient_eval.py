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
import random
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from ai_model.inference.openecg_adapter import OpenEcgClassifier
from ai_model.quality.coach import assess_signal_quality


TASK_LABELS = ('normal', 'atrial_fibrillation', 'other_abnormality')
ABSTAIN = 'abstain'
MODEL_VERSION_FALLBACK = 'openecg-codec-v6'
LABEL_MAPPING_VERSION = 'ptbxl-rhythm-only-v3'
AF_CODES = {'AFIB'}
OTHER_RHYTHM_CODES = {
    'AFLT', 'SVTAC', 'SARRH', 'SBRAD', 'STACH',
    'PAC', 'PVC', 'BIGU', 'TRIGU', 'PSVT',
}
SUPPORTED_RHYTHM_CODES = AF_CODES | OTHER_RHYTHM_CODES


def _parse_codes(value: str) -> dict[str, float]:
    parsed = ast.literal_eval(value)
    if not isinstance(parsed, dict):
        raise ValueError('scp_codes must be a dictionary')
    return {str(code).upper(): float(weight) for code, weight in parsed.items()}


def map_ptbxl_label_detail(scp_codes: dict[str, float]) -> dict[str, Any]:
    """Map conservative PTB-XL record labels to the OpenECG task labels.

    NORM is accepted as normal only when no competing diagnostic superclass or
    arrhythmia label is present. AFIB is accepted as a distinct class only when
    PTB-XL explicitly includes AFIB. Other diagnosed records map to the broad
    other_abnormality bucket. Records without a supported diagnosis are omitted.
    """
    # PTB-XL stores some rhythm statements with likelihood 0 because the
    # likelihood field is not applicable. Presence of a supported rhythm code
    # therefore matters; filtering only values > 0 would silently drop AFIB.
    codes = {str(code).upper() for code in scp_codes}
    rhythm_codes = sorted(codes & SUPPORTED_RHYTHM_CODES)
    if codes & AF_CODES:
        competing = sorted((codes & OTHER_RHYTHM_CODES) | (codes & {'NORM'}))
        if competing:
            return {
                'label': None,
                'mapping_status': 'excluded_ambiguous_rhythm',
                'mapping_reason': 'AFIB coexists with other supported rhythm codes',
                'rhythm_codes': rhythm_codes,
            }
        return {
            'label': 'atrial_fibrillation',
            'mapping_status': 'included',
            'mapping_reason': 'explicit AFIB rhythm statement',
            'rhythm_codes': rhythm_codes,
        }
    if codes & OTHER_RHYTHM_CODES:
        return {
            'label': 'other_abnormality',
            'mapping_status': 'included',
            'mapping_reason': 'explicit supported non-AF rhythm statement',
            'rhythm_codes': rhythm_codes,
        }
    if 'NORM' in codes and codes <= {'NORM', 'SR'} and scp_codes.get('NORM', 0) > 0:
        return {
            'label': 'normal',
            'mapping_status': 'included',
            'mapping_reason': 'positive NORM with optional compatible SR statement only',
            'rhythm_codes': sorted(codes & {'SR'}),
        }
    return {
        'label': None,
        'mapping_status': 'excluded_task_mismatch',
        'mapping_reason': 'no supported rhythm truth; morphology/diagnosis is outside the current task',
        'rhythm_codes': rhythm_codes,
    }


def map_ptbxl_label(scp_codes: dict[str, float]) -> str | None:
    return map_ptbxl_label_detail(scp_codes)['label']


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
        parsed_codes = _parse_codes(row['scp_codes'])
        mapping = map_ptbxl_label_detail(parsed_codes)
        split = 'final_test' if fold == 10 else 'threshold_development' if fold == 9 else 'train_reference'
        manifest.append({
            'record_id': str(row['ecg_id']),
            'patient_id': patient_id,
            'fold': fold,
            'split': split,
            'true_label': mapping['label'],
            'mapping_status': mapping['mapping_status'],
            'mapping_reason': mapping['mapping_reason'],
            'rhythm_codes': '|'.join(mapping['rhythm_codes']),
            'scp_codes': json.dumps(parsed_codes, ensure_ascii=False, sort_keys=True),
            'record_path': row['filename_hr'],
            'sample_rate_hz': 500,
            'lead': 'II',
            'label_mapping_version': LABEL_MAPPING_VERSION,
        })
    leaked = {patient: sorted(folds) for patient, folds in patient_folds.items() if len(folds) > 1}
    if leaked:
        raise ValueError(f'Patient leakage across PTB-XL folds: {list(leaked.items())[:5]}')
    return manifest


def sample_patient_disjoint_fold(
    manifest: list[dict[str, Any]],
    fold: int,
    per_class: int,
    seed: int,
) -> list[dict[str, Any]]:
    if per_class < 1:
        raise ValueError('per_class must be positive')
    selected: list[dict[str, Any]] = []
    used_patients: set[str] = set()
    rng = random.Random(seed)
    for label in TASK_LABELS:
        by_patient: dict[str, list[dict[str, Any]]] = {}
        for row in manifest:
            if row['fold'] == fold and row['true_label'] == label:
                by_patient.setdefault(row['patient_id'], []).append(row)
        patients = sorted(by_patient)
        rng.shuffle(patients)
        added = 0
        for patient_id in patients:
            if patient_id in used_patients:
                continue
            patient_rows = sorted(by_patient[patient_id], key=lambda row: row['record_id'])
            selected.append(patient_rows[0])
            used_patients.add(patient_id)
            added += 1
            if added == per_class:
                break
        if added < per_class:
            raise ValueError(
                f'Fold {fold} has only {added} patient-disjoint {label} records; '
                f'requested {per_class}'
            )
    return sorted(selected, key=lambda row: (row['true_label'], row['record_id']))


def download_ptbxl_records(
    rows: list[dict[str, Any]],
    records_root: Path,
    base_url: str,
) -> dict[str, int]:
    downloaded = skipped = 0
    for row in rows:
        relative = Path(row['record_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'Unsafe PTB-XL record path: {relative}')
        for suffix in ('.hea', '.dat'):
            target = records_root / relative.with_suffix(suffix)
            if target.exists() and target.stat().st_size > 0:
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f"{base_url.rstrip('/')}/{relative.as_posix()}{suffix}"
            request = urllib.request.Request(
                url, headers={'User-Agent': 'health-system-v2-ptbxl-eval/1.0'}
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    content = response.read()
            except (urllib.error.URLError, TimeoutError) as exc:
                raise RuntimeError(f'Failed downloading {url}: {exc}') from exc
            if not content:
                raise RuntimeError(f'Empty download: {url}')
            target.write_bytes(content)
            downloaded += 1
    return {'downloaded_files': downloaded, 'already_present_files': skipped}


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


def classify_error(row: dict[str, Any]) -> str:
    truth = row.get('true_label')
    predicted = row.get('evaluated_label', ABSTAIN)
    failure = str(row.get('failure_reason') or '')
    if row.get('decision_state') == 'evaluation_error':
        return 'runtime_or_input_error'
    if predicted == ABSTAIN:
        if failure.startswith('quality_gate'):
            return 'quality_gate_rejection'
        if 'confidence' in failure:
            return 'confidence_rejection'
        return 'model_rejection'
    if truth != 'normal' and predicted == 'normal':
        return 'abnormal_missed_as_normal'
    if truth == 'normal' and predicted != 'normal':
        return 'normal_false_alarm'
    if truth != predicted:
        return 'abnormal_cross_class_error'
    return 'correct'


def build_error_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    misses_by_truth: dict[str, int] = {}
    for row in rows:
        category = classify_error(row)
        row['error_category'] = category
        counts[category] = counts.get(category, 0) + 1
        if category == 'abnormal_missed_as_normal':
            truth = str(row.get('true_label'))
            misses_by_truth[truth] = misses_by_truth.get(truth, 0) + 1
    abnormal_rows = [row for row in rows if row.get('true_label') != 'normal']
    missed = counts.get('abnormal_missed_as_normal', 0)
    return {
        'error_category_counts': counts,
        'abnormal_records': len(abnormal_rows),
        'abnormal_missed_as_normal': missed,
        'abnormal_miss_rate': _safe_divide(missed, len(abnormal_rows)),
        'misses_by_true_label': misses_by_truth,
        'review_priority': [
            'First review abnormal_missed_as_normal records.',
            'Confirm rhythm-code truth and lead II waveform before calling a case a model miss.',
            'Separate quality/input failures from classifier errors.',
        ],
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
    per_class_limit: int | None = None,
    seed: int = 20261025,
    exclude_reviewed_ids: set[str] | None = None,
) -> dict[str, Any]:
    manifest = patient_fold_manifest(metadata_path)
    reviewed_patients = {
        row['patient_id'] for row in manifest
        if row['record_id'] in (exclude_reviewed_ids or set())
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / 'ptbxl_patient_fold_manifest.csv'
    with manifest_path.open('w', encoding='utf-8-sig', newline='') as file:
        fields = [
            'record_id', 'patient_id', 'fold', 'split', 'true_label',
            'mapping_status', 'mapping_reason', 'rhythm_codes', 'scp_codes',
            'record_path', 'sample_rate_hz', 'lead', 'label_mapping_version',
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in fields} for row in manifest)
    selected = [
        row for row in manifest
        if row['fold'] in folds and row['true_label'] is not None
        and row['patient_id'] not in reviewed_patients
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
    if per_class_limit is not None:
        rng = random.Random(seed)
        sampled = []
        for label in TASK_LABELS:
            candidates = sorted(
                [row for row in selected if row['true_label'] == label],
                key=lambda row: row['record_id'],
            )
            rng.shuffle(candidates)
            sampled.extend(candidates[:per_class_limit])
        selected = sampled
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

    error_analysis = build_error_analysis(predictions)
    report = {
        'report_date': date.today().isoformat(),
        'dataset': 'PhysioNet PTB-XL v1.0.3, 500 Hz records',
        'task': 'record-level rhythm screening; not beat classification or clinical validation',
        'split': {
            'train_reference_folds': list(range(1, 9)),
            'threshold_development_fold': 9,
            'final_test_fold': 10,
            'evaluated_folds': sorted(folds),
            'patient_disjoint_check': 'passed_for_official_strat_fold_metadata',
            'test_records_selected': len(selected),
            'test_patients_selected': len({row['patient_id'] for row in selected}),
            'record_id_subset': sorted(record_ids) if record_ids is not None else None,
            'per_class_limit': per_class_limit,
            'selection_seed': seed,
            'excluded_reviewed_patient_count': len(reviewed_patients),
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
        'error_analysis': error_analysis,
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
    (output_dir / 'ptbxl_error_analysis.json').write_text(
        json.dumps(error_analysis, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    with (output_dir / 'ptbxl_errors.csv').open('w', encoding='utf-8-sig', newline='') as file:
        fields = [
            'record_id', 'patient_id', 'fold', 'true_label', 'predicted_label',
            'evaluated_label', 'confidence', 'quality_score', 'decision_state',
            'failure_reason', 'error_category', 'mapping_reason',
            'rhythm_codes', 'record_path', 'model_version',
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {key: row.get(key) for key in fields}
            for row in predictions
            if row.get('evaluated_label') != row.get('true_label')
        )
    with (output_dir / 'ptbxl_false_negatives.csv').open(
        'w', encoding='utf-8-sig', newline=''
    ) as file:
        fields = [
            'record_id', 'patient_id', 'fold', 'true_label', 'predicted_label',
            'confidence', 'quality_score', 'mapping_reason', 'rhythm_codes',
            'record_path', 'model_version',
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {key: row.get(key) for key in fields}
            for row in predictions
            if row.get('error_category') == 'abnormal_missed_as_normal'
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True, help='Path to ptbxl_database.csv')
    parser.add_argument('--output-dir', type=Path, default=Path('runtime/ptbxl_eval'))
    parser.add_argument(
        '--folds', default='10',
        help='Folds to evaluate. Use 9 for threshold development and 10 for final test.',
    )
    parser.add_argument('--lead', default='II')
    parser.add_argument('--confidence-threshold', type=float, default=0.55)
    parser.add_argument('--quality-threshold', type=float, default=70.0)
    parser.add_argument('--record-ids', help='Optional comma-separated ECG IDs for a smoke-test subset')
    parser.add_argument('--per-class-limit', type=int, help='Deterministic maximum records per class')
    parser.add_argument('--seed', type=int, default=20261025)
    parser.add_argument('--exclude-reviewed-ids', default='', help='Exclude all patients of these previously reviewed ECG IDs')
    parser.add_argument('--sample-fold', type=int, choices=(9, 10), help='Create a deterministic patient-disjoint sample manifest for fold 9 or 10')
    parser.add_argument('--per-class', type=int, default=100, help='Records per class when --sample-fold is used')
    parser.add_argument('--download', action='store_true', help='Download sampled WFDB files from PhysioNet')
    parser.add_argument('--records-root', type=Path, help='PTB-XL root containing records500/; used by inference or sample download')
    parser.add_argument('--physionet-base-url', default='https://physionet.org/files/ptb-xl/1.0.3', help='Dataset release URL')
    parser.add_argument('--manifest-only', action='store_true', help='Export patient-disjoint labeled manifest without model inference')
    args = parser.parse_args()
    if args.per_class_limit is not None and args.per_class_limit < 1:
        parser.error('--per-class-limit must be positive')
    if args.sample_fold is not None:
        if args.per_class < 1:
            parser.error('--per-class must be positive')
        if args.download and not args.records_root:
            parser.error('--records-root is required with --download')
        manifest = patient_fold_manifest(args.metadata)
        sampled = sample_patient_disjoint_fold(
            manifest, args.sample_fold, args.per_class, args.seed
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        target = args.output_dir / f'ptbxl_fold{args.sample_fold}_sample_manifest.csv'
        fields = [
            'record_id', 'patient_id', 'fold', 'split', 'true_label',
            'mapping_status', 'mapping_reason', 'rhythm_codes', 'scp_codes',
            'record_path', 'sample_rate_hz', 'lead', 'label_mapping_version',
        ]
        with target.open('w', encoding='utf-8-sig', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows({key: row.get(key) for key in fields} for row in sampled)
        summary = {label: sum(row['true_label'] == label for row in sampled) for label in TASK_LABELS}
        print(f'Sample manifest: {target.resolve()}')
        print(f'Fold {args.sample_fold} patient-disjoint sample: {summary}')
        if args.download:
            download_stats = download_ptbxl_records(
                sampled, args.records_root, args.physionet_base_url
            )
            print(f'Download summary: {download_stats}')
        return
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
        fields = [
            'record_id', 'patient_id', 'fold', 'split', 'true_label',
            'mapping_status', 'mapping_reason', 'rhythm_codes', 'scp_codes',
            'record_path', 'sample_rate_hz', 'lead', 'label_mapping_version',
        ]
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
        args.per_class_limit,
        args.seed,
        {part.strip() for part in args.exclude_reviewed_ids.split(',') if part.strip()},
    )
    print(json.dumps(report['metrics'], ensure_ascii=False, indent=2))
    print(f"Full report: {args.output_dir.resolve() / 'ptbxl_metrics.json'}")


if __name__ == '__main__':
    main()
