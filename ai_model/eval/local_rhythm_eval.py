"""Freeze and evaluate locally available PTB-XL records under the v3 mapping."""
import argparse
import json
from collections import Counter
from pathlib import Path

from ai_model.eval.ptbxl_patient_eval import patient_fold_manifest, run_evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--records-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--fold', type=int, choices=(9, 10), default=9)
    args = parser.parse_args()
    manifest = patient_fold_manifest(args.metadata)
    local = [row for row in manifest if row['fold'] == args.fold and all(
        (args.records_root / (row['record_path'] + ext)).is_file() for ext in ('.hea', '.dat'))]
    selected = [row for row in local if row['true_label'] is not None]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selection = {
        'scope': 'available local records; not a representative or unseen test set',
        'fold': args.fold, 'local_records': len(local), 'included_records': len(selected),
        'excluded_records': [row for row in local if row['true_label'] is None],
        'class_counts': dict(Counter(row['true_label'] for row in selected)),
        'record_ids': [row['record_id'] for row in selected],
    }
    (args.output_dir / 'selection_audit.json').write_text(
        json.dumps(selection, ensure_ascii=False, indent=2), encoding='utf-8')
    if not selected:
        raise ValueError('No eligible locally available records; see selection_audit.json')
    report = run_evaluation(args.metadata, args.records_root, args.output_dir, {args.fold},
                            record_ids={row['record_id'] for row in selected})
    print(json.dumps({'selection': {k: v for k, v in selection.items() if k != 'excluded_records'},
                      'metrics': report['metrics'], 'error_analysis': report['error_analysis']},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
