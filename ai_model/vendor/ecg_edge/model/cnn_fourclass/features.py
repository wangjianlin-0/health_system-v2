"""H27的122项形态特征和8项历史RR；无拟合、无标签或后继RR输入。"""
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'model/inference'))
from ecg_model.ecg_relative_features import relative_features

def rr_sequence(positions,valid):
    p=np.asarray(positions,np.int64);valid=np.asarray(valid,bool)
    if p.ndim!=1 or valid.shape!=p.shape or np.any(np.diff(p)<=0):raise ValueError('RR时间轴无效')
    out=np.zeros((len(p),8),np.float32)
    if len(p)<2:return out
    delta=np.r_[0,np.diff(p)].astype(float)
    for i in range(1,len(p)):
        h=delta[max(1,i-32):i];med=np.median(h) if len(h) else delta[i]
        values=delta[max(1,i-7):i+1];out[i,-len(values):]=np.clip(values/med,0,4)/4
    out[~valid]=0;return out

def hand_features(x,rr,background,count):
    values,names=relative_features(x,rr,background,count)
    if values.shape!=(len(x),122):raise ValueError('要求122项固定因果特征')
    return values
