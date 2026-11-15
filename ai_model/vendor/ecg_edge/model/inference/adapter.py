"""供网页后端导入的JSON安全适配函数；不替换队友现有服务。"""
from ecg_model import infer_mv

def analyze_ecg(samples_mv,*,fold,preprocess,sampling_hz=500):
    """每次传一条连续记录；独立调用不保留分块之间的状态。"""
    r=infer_mv(samples_mv,fold=fold,preprocess=preprocess,sampling_hz=sampling_hz)
    beats=[]
    for i,pos in enumerate(r['positions500']):
        valid=bool(r['valid'][i])
        beats.append(dict(beat_id=i+1,r_sample500=int(pos),r_seconds=float(pos/500),
            waveform_ready_sample500=int(r['ready500'][i]),decision_sample500=int(r['decision_at'][i]),
            input_status=int(r['status'][i]),valid=valid,label=str(r['labels'][i]),
            class_id=int(r['class_id'][i]),probabilities=[float(p) for p in r['probabilities'][i]] if valid else None))
    return dict(model='HGB-v92',fold=fold,classes=['N','S','VF'],VF_definition='V/E/F合并，非心室颤动',
        sampling_hz=500,input_unit='mV',preprocess=preprocess,clipped_samples=int(r['clipped_samples']),
        qualified=False,beats=beats)
