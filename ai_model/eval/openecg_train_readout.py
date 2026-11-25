"""Fit a four-class readout on PTB-XL and audit it on external CODE-test ECGs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from scipy.signal import resample_poly
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

import openecg

from ai_model.eval.ptbxl_patient_eval import _load_ptbxl_record

LABELS = ('sinus', 'avb', 'afib', 'bbb')
CODE_COLUMNS = ('1dAVb', 'RBBB', 'LBBB', 'SB', 'ST', 'AF')
CODE_INDEX = (1, 3, 3, 0, 0, 2)
HEAD_INDEX = (0, 1, 3, 4)


def features(signals, temporal_stats=False, exclude_padding=False):
    model = openecg.load_codec()
    embeddings = []
    logits = []

    def pool_input(_module, inputs):
        activations = inputs[0]
        pooled = pool(activations)
        if temporal_stats:
            if mask is None:
                spread = activations.std(dim=1, correction=0)
                peak = activations.amax(dim=1)
            else:
                spread = pool((activations - pooled[:, None]).square()).sqrt()
                peak = activations.masked_fill(~mask, -torch.inf).amax(dim=1)
            pooled = torch.cat((pooled, spread, peak), dim=1)
        embeddings.append(pooled.cpu().numpy())

    def pool(activations):
        if mask is None:
            return activations.mean(dim=1)
        return (activations * mask).sum(dim=1) / mask.sum(dim=1)

    handle = model.rhythm_sample.register_forward_pre_hook(pool_input)
    try:
        with torch.inference_mode():
            for start in range(0, len(signals), 16):
                batch = signals[start:start + 16]
                mask = None
                if exclude_padding:
                    nonzero = np.asarray(batch) != 0
                    observed = np.maximum.accumulate(nonzero, axis=1) & np.maximum.accumulate(
                        nonzero[:, ::-1], axis=1)[:, ::-1]
                    observed[~nonzero.any(axis=1)] = True
                    mask = torch.from_numpy(observed[..., None])
                inputs = np.stack([openecg.rank_normalize(signal) for signal in batch])
                windows = torch.from_numpy(inputs.astype(np.float32))
                output = model(windows, torch.zeros(len(batch), dtype=torch.long))[-1]
                logits.append(pool(output)[:, HEAD_INDEX].cpu().numpy())
    finally:
        handle.remove()
    return np.concatenate(embeddings), np.concatenate(logits)


def score(labels, scores):
    predicted = scores.argmax(axis=1)
    return {
        'samples': len(labels), 'accuracy': float(np.mean(predicted == labels)),
        'macro_f1': f1_score(labels, predicted, labels=range(len(LABELS)), average='macro'),
        'f1': dict(zip(LABELS, f1_score(labels, predicted, labels=range(len(LABELS)),
                                        average=None).tolist(), strict=True)),
        'auroc': {name: roc_auc_score(labels == idx, scores[:, idx])
                  for idx, name in enumerate(LABELS)},
    }


def calibrate_bias(labels, scores, weights):
    def objective(offset):
        return f1_score(labels, (scores + offset).argmax(axis=1), average='macro',
                        labels=range(len(LABELS)), sample_weight=weights)

    offset = np.zeros(len(LABELS))
    for _ in range(3):
        for class_index in range(1, len(LABELS)):
            candidates = np.tile(offset, (33, 1))
            candidates[:, class_index] = np.linspace(-8, 8, 33)
            offset = max(candidates, key=objective)
    return offset


def code_test(hdf5_path, annotations_path):
    import h5py

    with annotations_path.open(encoding='utf-8-sig', newline='') as stream:
        annotations = list(csv.DictReader(stream))
    selected = []
    labels = []
    for idx, row in enumerate(annotations):
        flags = {value for key, value in zip(CODE_COLUMNS, CODE_INDEX, strict=True)
                 if row[key].strip().lower() in {'true', '1', '1.0'}}
        # SB and ST describe sinus rate and can coexist with a conduction defect.
        if flags - {0}:
            flags.discard(0)
        if len(flags) <= 1:
            selected.append(idx)
            labels.append(next(iter(flags), 0))

    with h5py.File(hdf5_path) as source:
        traces = source['tracings']
        if len(traces) != len(annotations) or traces.ndim != 3 or traces.shape[-1] != 12:
            raise ValueError('CODE-test ECGs and annotations are not aligned')
        windows = np.empty((len(selected), 5000), dtype=np.float32)
        for pos, idx in enumerate(selected):
            lead_ii = traces[idx, :, 1]
            if len(lead_ii) < 4000:
                raise ValueError('Expected at least ten seconds at 400 Hz')
            offset = (len(lead_ii) - 4000) // 2
            windows[pos] = resample_poly(lead_ii[offset:offset + 4000], 5, 4)
    return windows, np.asarray(labels), selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--records-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--code-ecg', type=Path)
    parser.add_argument('--code-labels', type=Path)
    parser.add_argument('--sinus-prior', type=float, default=0.25)
    parser.add_argument('--augment-short', action='store_true',
                        help='Train on full and center-padded seven-second ECGs')
    parser.add_argument('--calibrate-logits', action='store_true',
                        help='Fit the readout on the original four rhythm logits')
    parser.add_argument('--calibrate-bias', action='store_true',
                        help='Fit class offsets on the PTB-XL validation split')
    parser.add_argument('--rbf', action='store_true', help='Fit an RBF kernel readout')
    parser.add_argument('--temporal-stats', action='store_true',
                        help='Include temporal variation and peak activations')
    parser.add_argument('--exclude-padding', action='store_true',
                        help='Exclude zero padding from record-level feature pooling')
    args = parser.parse_args()
    if bool(args.code_ecg) != bool(args.code_labels):
        parser.error('Pass both CODE-test files together')

    torch.set_num_threads(4)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if len({row['patient_id'] for row in manifest}) != len(manifest):
        raise ValueError('Expected one ECG per PTB-XL patient')

    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    feature_suffix = '_temporal' if args.temporal_stats else ''
    if args.exclude_padding:
        feature_suffix += '_unpadded'
    cache = args.output_dir / f'ptbxl_features_{manifest_hash[:16]}{feature_suffix}.npz'
    if cache.is_file():
        with np.load(cache) as saved:
            embedding, logits = saved['embedding'], saved['logits']
    else:
        signals = [_load_ptbxl_record(args.records_root / row['record_path'], 'II')[:5000]
                   for row in manifest]
        embedding, logits = features(signals, args.temporal_stats, args.exclude_padding)
        np.savez_compressed(cache, embedding=embedding, logits=logits)

    labels = np.array([row['label'] for row in manifest])
    train = np.array([row['split'] == 'train' for row in manifest])
    if args.calibrate_logits:
        embedding = logits
    fit_features, fit_labels = embedding[train], labels[train]
    if args.augment_short:
        short_signals = []
        for row in manifest:
            signal = _load_ptbxl_record(args.records_root / row['record_path'], 'II')[:5000]
            short_signals.append(np.pad(signal[750:4250], (750, 750)))
        short_embedding, short_logits = features(short_signals, args.temporal_stats, args.exclude_padding)
        if args.calibrate_logits:
            short_embedding = short_logits
        fit_features = np.concatenate((fit_features, short_embedding[train]))
        fit_labels = np.tile(fit_labels, 2)
        validation_features = np.concatenate((embedding[~train], short_embedding[~train]))
        validation_logits = np.concatenate((logits[~train], short_logits[~train]))
        validation_labels = np.tile(labels[~train], 2)
    else:
        validation_features = embedding[~train]
        validation_logits = logits[~train]
        validation_labels = labels[~train]
    baseline = score(labels[~train], logits[~train])
    if not 0.25 <= args.sinus_prior < 1:
        parser.error('--sinus-prior must be in [0.25, 1)')
    prior = np.array([args.sinus_prior] + [(1 - args.sinus_prior) / 3] * 3)
    weights = prior[validation_labels]
    def objective(scores):
        return f1_score(validation_labels, scores.argmax(axis=1),
                        labels=range(len(LABELS)), average='macro', sample_weight=weights)

    zero_bias = np.zeros(len(LABELS))
    best = (objective(validation_logits), 0.0, None, None, zero_bias)
    for penalty in (0.01, 0.1, 1.0, 10.0):
        classifier = (SVC(C=penalty, probability=True, random_state=12) if args.rbf
                      else LogisticRegression(C=penalty, max_iter=2000))
        predictor = make_pipeline(StandardScaler(), classifier)
        predictor.fit(fit_features, fit_labels)
        learned = predictor.decision_function(validation_features)
        for weight in (0.1, 0.25, 0.5, 0.75, 1.0):
            combined = (1 - weight) * validation_logits + weight * learned
            biases = [strength * np.log(4 * prior) for strength in (0.0, 0.5, 1.0, 1.5, 2.0)]
            if args.calibrate_bias:
                biases.append(calibrate_bias(validation_labels, combined, weights))
            for bias in biases:
                result = objective(combined + bias)
                if result > best[0]:
                    best = (result, weight, penalty, predictor, bias)

    _, weight, penalty, predictor, bias = best
    validation = baseline if predictor is None else score(
        labels[~train], (1 - weight) * logits[~train]
        + weight * predictor.decision_function(embedding[~train]) + bias
    )
    report = {'manifest_sha256': manifest_hash, 'label_order': LABELS,
              'train_records': int(train.sum()), 'blend_weight': weight, 'C': penalty,
              'sinus_prior': args.sinus_prior, 'class_bias': bias.tolist(),
              'augment_short': args.augment_short,
              'calibrate_logits': args.calibrate_logits,
              'calibrate_bias': args.calibrate_bias,
              'rbf': args.rbf,
              'temporal_stats': args.temporal_stats,
              'exclude_padding': args.exclude_padding,
              'validation_baseline': baseline, 'validation_selected': validation}
    if predictor is not None:
        scaler, readout = predictor.steps[0][1], predictor.steps[1][1]
        if args.rbf:
            import joblib

            joblib.dump(predictor, args.output_dir / 'readout.joblib')
        else:
            np.savez_compressed(args.output_dir / 'readout.npz', mean=scaler.mean_, scale=scaler.scale_,
                                coef=readout.coef_, intercept=readout.intercept_, weight=weight,
                                class_bias=bias)
    print('PTB-XL validation', baseline['macro_f1'], validation['macro_f1'], flush=True)
    if args.code_ecg:
        windows, truth, selected = code_test(args.code_ecg, args.code_labels)
        embedding, logits = features(windows, args.temporal_stats, args.exclude_padding)
        if args.calibrate_logits:
            embedding = logits
        external = logits if predictor is None else (
            (1 - weight) * logits + weight * predictor.decision_function(embedding) + bias
        )
        report['code_test_baseline'] = score(truth, logits)
        report['code_test_selected'] = score(truth, external)
        np.savez_compressed(args.output_dir / 'code_test_predictions.npz', rows=selected,
                            truth=truth, baseline_scores=logits, selected_scores=external)
    (args.output_dir / 'training_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
