"""隔离调用比赛项目冻结权重；电脑CPU推理，不训练、不访问板卡。"""
from pathlib import Path
import hashlib
import json
import sys

VENDOR = Path(__file__).resolve().parents[1] / 'vendor' / 'ecg_edge'
MODULE = VENDOR / 'model' / 'inference'


def verify_assets():
    manifest = json.loads((VENDOR / 'migration_manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path = (VENDOR / name).resolve()
        if not path.is_relative_to(VENDOR.resolve()):
            raise ValueError('非法资产路径')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('迁入资产校验失败：' + name)


def run(payload):
    verify_assets()
    sys.path[:0] = [str(VENDOR), str(MODULE)]
    kind = payload['model']
    if kind == 'hgb':
        from adapter import analyze_ecg
        result = analyze_ecg(payload['samples'], fold=0, preprocess='hp05', sampling_hz=500)
        asset = MODULE / 'assets' / 'v92_fold0.npz'
    elif kind == 'cnn':
        import numpy as np
        import torch
        from model.cnn_fourclass.network import classify_mv
        torch.set_num_threads(4)
        raw = classify_mv(payload['samples'], fold=0, preprocess='hp05', sampling_hz=500)
        beats = []
        for i, position in enumerate(raw['positions500']):
            valid = bool(raw['valid'][i])
            probabilities = None
            if valid:
                logits = raw['logits'][i].astype(float)
                exp = np.exp(logits - logits.max())
                probabilities = (exp / exp.sum()).tolist()
            class_id = int(raw['prediction'][i])
            beats.append(dict(beat_id=i + 1, r_sample500=int(position), r_seconds=float(position / 500),
                waveform_ready_sample500=int(raw['ready500'][i]), decision_sample500=int(raw['ready500'][i]),
                valid=valid, class_id=class_id, label=['N', 'S', 'V', 'F'][class_id] if valid else 'UNCLASSIFIED',
                probabilities=probabilities))
        result = dict(classes=['N', 'S', 'V', 'F'], beats=beats, clipped_samples=raw['clipped_samples'])
        asset = VENDOR / 'model' / 'cnn_fourclass' / 'assets' / 'fold_0.pt'
    else:
        raise ValueError('只支持cnn/hgb')
    result['model_sha256'] = hashlib.sha256(asset.read_bytes()).hexdigest()
    return result


if __name__ == '__main__':
    try:
        body = sys.stdin.buffer.read(8_000_001)
        if len(body) > 8_000_000:
            raise ValueError('输入过大')
        print(json.dumps(run(json.loads(body)), ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(2)
