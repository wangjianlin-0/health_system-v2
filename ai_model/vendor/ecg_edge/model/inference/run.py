"""单列CSV/NPY的500Hz单导联mV→逐拍N/S/VF研究推理。"""
import argparse,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ecg_model import infer_mv
import numpy as np

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True,help='无标题单列mV CSV或一维NPY')
    p.add_argument('--fold',type=int,choices=[0,1,2],required=True)
    p.add_argument('--preprocess',choices=['raw','hp05'],required=True)
    p.add_argument('--sampling-hz',type=int,default=500)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--features',type=Path,help='可选：保存全部192特征、波形与时序NPZ')
    a=p.parse_args()
    # 输入不允许pickle；CSV只含一列，避免把时间列或ADC码误当mV。
    if a.input.suffix.lower()=='.npy':x=np.load(a.input,allow_pickle=False)
    else:
        x=np.loadtxt(a.input,delimiter=',',ndmin=2)
        if x.shape[1]!=1:raise ValueError('CSV必须是无标题的单列mV，不能含时间列或多个导联')
        x=x[:,0]
    if a.output.exists() or (a.features and a.features.exists()):raise FileExistsError('输出已存在，请选择新路径')
    if a.features and (a.features.suffix.lower()!='.npz' or a.features.resolve()==a.output.resolve()):raise ValueError('--features必须为另一个.npz文件')
    r=infer_mv(x,fold=a.fold,preprocess=a.preprocess,sampling_hz=a.sampling_hz)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['beat_id','r_sample500','r_seconds','waveform_ready_sample500','decision_sample500','decision_seconds','input_status','valid','class_id','label','p_N','p_S','p_VF','research_fold'])
        for i,pos in enumerate(r['positions500']):
            prob=[float(v) if np.isfinite(v) else '' for v in r['probabilities'][i]]
            w.writerow([i+1,int(pos),pos/500,int(r['ready500'][i]),int(r['decision_at'][i]),r['decision_at'][i]/500,int(r['status'][i]),bool(r['valid'][i]),int(r['class_id'][i]),r['labels'][i],*prob,a.fold])
    if a.features:
        a.features.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(a.features,**r)
    print(json.dumps(dict(samples=len(x),events=len(r['valid']),classified=int(r['valid'].sum()),clipped_samples=int(r['clipped_samples']),features=192,fold=a.fold,preprocess=a.preprocess,fits=0,qualified=False,output=str(a.output)),ensure_ascii=False))
if __name__=='__main__':main()
