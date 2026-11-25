"""Recompute saved PTB-XL metrics without waveform loading or model inference."""
import argparse
import json
import math
from pathlib import Path

from ai_model.eval.ptbxl_patient_eval import evaluate_predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', type=Path, default=Path('runtime/ptbxl_report'))
    args = parser.parse_args()
    rows = json.loads((args.report_dir / 'ptbxl_predictions.json').read_text(encoding='utf-8'))
    saved = json.loads((args.report_dir / 'ptbxl_metrics.json').read_text(encoding='utf-8'))
    computed = evaluate_predictions(rows)

    def compare(actual, expected, path='metrics'):
        if isinstance(expected, dict):
            for key, value in expected.items():
                compare(actual[key], value, f'{path}.{key}')
        elif isinstance(expected, (int, float)):
            if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12):
                raise ValueError(f'{path}: recomputed={actual}, saved={expected}')
        elif actual != expected:
            raise ValueError(f'{path}: recomputed={actual!r}, saved={expected!r}')

    compare(computed, saved['metrics'])
    print(json.dumps({'verified': True, 'scope': 'saved predictions only; no inference',
                      'patients': len({r['patient_id'] for r in rows}),
                      'metrics': computed}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
