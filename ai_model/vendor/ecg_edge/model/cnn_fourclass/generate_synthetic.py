"""固定随机数自检向量：不读取任何患者记录、数据缓存或训练软目标。"""
from pathlib import Path
import argparse
import numpy as np
from network import load_model,logits
HERE=Path(__file__).resolve().parent

def vectors(fold):
    rng=np.random.default_rng(2026110200+fold)
    x=rng.normal(size=(12,128)).astype(np.float32)
    x[0]=0;x[1]=1;x[2]=np.tile([-1,1],64)
    rr=rng.uniform(0,.7,size=(12,3)).astype(np.float32)
    background=rng.normal(size=(12,128)).astype(np.float32)
    count=np.arange(12,dtype=np.int8)%9
    history=rng.uniform(0,1,size=(12,8)).astype(np.float32)
    return dict(x=x,rr=rr,background=background,history_count=count,history_rr=history)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,help='可选写出新目录；默认核验已有合成文件')
    args=p.parse_args()
    if args.output:args.output.mkdir(parents=True,exist_ok=False)
    for f in range(3):
        z=vectors(f);z['logits']=logits(load_model(f),z['x'],z['rr'],z['background'],z['history_count'],z['history_rr'])
        if args.output:np.savez_compressed(args.output/f'golden_{f}.npz',**z)
        else:
            with np.load(HERE/f'assets/golden_{f}.npz',allow_pickle=False) as old:
                assert set(old.files)==set(z)
                for key in z:np.testing.assert_array_equal(z[key],old[key])
    print('SYNTHETIC_INPUTS_AND_LOGITS_EXACT: 36 fixed-seed random/constant vectors; no patient input files read; no training')
if __name__=='__main__':main()
