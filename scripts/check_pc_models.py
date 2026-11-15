"""离线核对资产、H27黄金向量和HGB整段合成结果；不训练、不访问硬件。"""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from ai_model.inference.edge_worker import VENDOR, MODULE, verify_assets


def main():
    verify_assets()
    subprocess.run([sys.executable, '-X', 'utf8', '-B', str(MODULE / 'check.py')], check=True)
    sys.path[:0] = [str(VENDOR), str(MODULE)]
    import numpy as np
    import torch
    from model.cnn_fourclass.network import load_model, logits
    torch.set_num_threads(4)
    for fold in range(3):
        with np.load(VENDOR / f'model/cnn_fourclass/assets/golden_{fold}.npz') as z:
            score = logits(load_model(fold), z['x'], z['rr'], z['background'], z['history_count'], z['history_rr'])
            np.testing.assert_allclose(score, z['logits'], rtol=1e-6, atol=1e-6)
            np.testing.assert_array_equal(score.argmax(1), z['logits'].argmax(1))
    from ai_model.inference.edge_adapter import EdgeClassifier
    samples = np.loadtxt(MODULE / 'examples/synthetic500.csv', delimiter=',').tolist()
    reports = {}
    for kind in ('cnn', 'hgb'):
        prediction = EdgeClassifier(kind).predict(dict(waveform_raw_mV=samples, sample_rate_hz=500, unit='mV'))
        assert prediction['status'] == 'classified', prediction
        reports[kind] = dict(model=prediction['model_version'], sha256=prediction['model_sha256'],
            counts=prediction['beats']['by_type'], events=prediction['beats']['count'],
            inference_ms=prediction['inference_ms'])
    out = ROOT / 'runtime/verification/pc_models.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(passed=True, hardware=False, training=False, models=reports), ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == '__main__':
    main()
