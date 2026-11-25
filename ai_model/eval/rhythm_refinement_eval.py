"""Compare waveform-based additions to a saved OpenECG PTB-XL baseline."""
import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

from ai_model.beat_detection.detector import RPeakDetector
from ai_model.eval.ptbxl_patient_eval import _load_ptbxl_record, evaluate_predictions
from ai_model.inference.edge_adapter import EdgeClassifier


@dataclass(frozen=True)
class RefinementRule:
    rate_margin: int
    minimum_beats: int
    beat_confidence: float

    def flags(self, evidence):
        bpm = evidence['bpm']
        rate_flag = bpm is not None and (
            bpm < 60 - self.rate_margin or bpm > 100 + self.rate_margin
        )
        beat_count = sum(score >= self.beat_confidence for score in evidence['ectopic_scores'])
        return rate_flag or beat_count >= self.minimum_beats


def extract_evidence(row, records_root):
    evidence = {'rate_flag': None, 'ectopic_beats': 0, 'beat_status': 'skipped',
                'bpm': None, 'rr_cv': None, 'ectopic_scores': []}
    if row['evaluated_label'] != 'normal':
        return evidence
    waveform = _load_ptbxl_record(records_root / row['record_path'], row['lead'])[:5000]
    peaks = RPeakDetector('neurokit2').detect(waveform, 500)
    if peaks['count'] >= 5:
        rate = peaks['heart_rate']
        bpm = rate['bpm']
        evidence.update(bpm=bpm, rr_cv=rate['rr_cv'])
        if bpm < 60:
            evidence['rate_flag'] = 'slow'
        elif bpm > 100:
            evidence['rate_flag'] = 'fast'
    beats = EdgeClassifier('cnn').predict({
        'waveform': waveform, 'sample_rate_hz': 500, 'unit': 'mV',
    })
    evidence['beat_status'] = beats['status']
    evidence['ectopic_scores'] = [
        beat['confidence']
        for beat in (beats.get('beats') or {}).get('items', [])
        if beat['valid'] and beat['label'] in {'S', 'V'} and beat['confidence'] is not None
    ]
    evidence['ectopic_beats'] = sum(score >= 0.9 for score in evidence['ectopic_scores'])
    return evidence


def compare(rows, evidence, rule=None):
    stages = {name: [] for name in ('baseline', 'rate', 'rate_and_beats', 'with_rr_variability')}
    if rule is not None:
        stages['optimized'] = []
    for row, signal in zip(rows, evidence, strict=True):
        label = row['evaluated_label']
        rate = bool(signal['rate_flag'])
        ectopy = signal['ectopic_beats'] >= 1
        variable = (signal['rr_cv'] or 0) > 0.2
        flags = (False, rate, rate or ectopy, rate or ectopy or variable)
        if rule is not None:
            flags += (rule.flags(signal),)
        for (name, stage), flagged in zip(stages.items(), flags, strict=True):
            stage.append({**row, 'evaluated_label': 'other_abnormality'
                          if label == 'normal' and flagged else label})
    return {name: evaluate_predictions(stage) for name, stage in stages.items()}, stages


def select_rule(rows, evidence):
    reference, _ = compare(rows, evidence)
    previous = reference['rate_and_beats']
    false_alarms = previous['per_class']['normal']['false_negative_including_abstentions']
    candidates = []
    for margin, minimum_beats, confidence in product((0, 3, 5, 8), (1, 2, 3), (0.9, 0.95, 0.98)):
        rule = RefinementRule(margin, minimum_beats, confidence)
        metrics, _ = compare(rows, evidence, rule)
        result = metrics['optimized']
        errors = result['per_class']['normal']['false_negative_including_abstentions']
        if errors <= false_alarms:
            candidates.append((result['correct'], -errors, rule))
    return max(candidates, key=lambda candidate: candidate[:2])[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--records-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--select-rule', type=Path, help='Select on fold 9 and write the frozen rule')
    mode.add_argument('--rule', type=Path, help='Compare a previously frozen rule')
    args = parser.parse_args()
    rows = json.loads(args.baseline.read_text(encoding='utf-8'))
    if not rows or len({str(row['record_id']) for row in rows}) != len(rows):
        parser.error('Baseline predictions must contain unique records')
    if args.select_rule and {row['fold'] for row in rows} != {9}:
        parser.error('Rule selection requires fold 9 predictions')
    rule = RefinementRule(**json.loads(args.rule.read_text(encoding='utf-8'))) if args.rule else None
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        evidence = list(pool.map(lambda row: extract_evidence(row, args.records_root), rows))
    if args.select_rule:
        rule = select_rule(rows, evidence)
        args.select_rule.parent.mkdir(parents=True, exist_ok=True)
        with args.select_rule.open('x', encoding='utf-8') as stream:
            json.dump(asdict(rule), stream, indent=2)
    metrics, stages = compare(rows, evidence, rule)
    report = {
        'baseline': str(args.baseline.resolve()),
        'folds': sorted({row['fold'] for row in rows}),
        'patient_count': len({row['patient_id'] for row in rows}),
        'settings': {'slow_below_bpm': 60, 'fast_above_bpm': 100, 'minimum_r_peaks': 5,
                     'beat_model': 'CNN-H27-fold0', 'beat_confidence_min': 0.9,
                     'minimum_ectopic_beats': 1, 'rr_cv_above': 0.2},
        'beat_status_counts': dict(Counter(item['beat_status'] for item in evidence)),
        'optimized_rule': asdict(rule) if rule is not None else None,
        'metrics': metrics,
        'predictions': [
            {**row, 'evidence': signal,
             'stage_labels': {name: stage[index]['evaluated_label'] for name, stage in stages.items()}}
            for index, (row, signal) in enumerate(zip(rows, evidence, strict=True))
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, stage in metrics.items():
        print(name, stage['correct'], '/', stage['samples'],
              'macro F1', round(stage['macro_f1_including_abstentions_as_missed'], 4))
    print(args.output.resolve())


if __name__ == '__main__':
    main()
