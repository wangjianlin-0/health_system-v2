"""校验文件、合成整段心电完整流水线与三份研究权重；不读取患者数据、不训练。"""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ecg_model import infer_mv
from ecg_model.tree_model import probability
import numpy as np
R=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rebuilt-native',action='store_true',help='明确已自行从源码重编译；跳过bin文件原包SHA，仍执行全部数值检查')
    a=p.parse_args()
    manifest=json.loads((R/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['qualified'] is False and manifest['fits']==0
    for name,spec in manifest['files'].items():
        if a.rebuilt_native and name.startswith('bin/'):continue
        path=(R/name).resolve();assert path.is_relative_to(R)
        content=path.read_bytes()
        if spec['lf_normalized']:content=content.replace(b'\r\n',b'\n')
        if hashlib.sha256(content).hexdigest()!=spec['sha256']:raise ValueError('文件校验失败：'+name)
    x=np.loadtxt(R/'examples/synthetic500.csv',delimiter=',')
    with np.load(R/'examples/synthetic_expected.npz',allow_pickle=False) as golden:
        for f in range(3):
            r=infer_mv(x,fold=f,preprocess='hp05')
            for key in ['requests','features','positions500','ready500','decision_at','valid']:
                np.testing.assert_array_equal(r[key],golden[key],err_msg=key)
            np.testing.assert_allclose(r['probabilities'],golden[f'probability_{f}'],atol=1e-12,rtol=1e-12,equal_nan=True)
            np.testing.assert_array_equal(r['class_id'][r['valid']],golden[f'probability_{f}'][r['valid']].argmax(1))
    with np.load(R/'examples/feature_vectors.npz',allow_pickle=False) as z:
        for f in range(3):
            with np.load(R/f'assets/v92_fold{f}.npz',allow_pickle=False) as model:
                np.testing.assert_allclose(probability(z['features'],model),z[f'probability_fold_{f}'],atol=1e-12,rtol=1e-12)
    empty=infer_mv(np.zeros(5000),fold=0,preprocess='raw');assert empty['features'].shape==(0,192)
    for kwargs in [dict(samples=np.array([np.nan]),fold=0,preprocess='raw'),dict(samples=np.zeros(10),fold=0,preprocess='raw',sampling_hz=360),dict(samples=np.zeros((10,2)),fold=0,preprocess='hp05')]:
        try:infer_mv(**kwargs)
        except ValueError:pass
        else:raise AssertionError('无效输入未拒绝')
    forbidden=[n for n in ('sklearn','joblib','wfdb','torch') if n in sys.modules]
    if forbidden:raise AssertionError('推理意外加载训练/数据依赖：'+str(forbidden))
    print(json.dumps(dict(passed=True,models=3,synthetic_samples=len(x),synthetic_events=len(r['valid']),synthetic_classified=int(r['valid'].sum()),features=192,maximum_feature_difference=0,feature_vectors=160,fits=0,training_libraries_loaded=forbidden,rebuilt_native=a.rebuilt_native,qualified=False),ensure_ascii=False))
if __name__=='__main__':main()
