"""可移植H27：单次残差CNN + 因果形态/RR + 64隐藏单元四类头。"""
from pathlib import Path
import json,sys
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'src/reference'),str(ROOT/'model/inference')]
from ecg_trainable_cnn import create_model
from ecg_model.ecg_relative_features import relative_features

def tensor(a):
    a=np.ascontiguousarray(a,dtype=np.int64 if np.asarray(a).dtype.kind in 'iu' else np.float32)
    return torch.frombuffer(a,dtype=torch.int64 if a.dtype.kind in 'iu' else torch.float32).reshape(a.shape).clone()

def rr_sequence(positions,valid):
    """当前及之前8个RR，按此前最多32间隔中位数缩放；无后继输入。"""
    p=np.asarray(positions,np.int64);valid=np.asarray(valid,bool)
    if p.ndim!=1 or valid.shape!=p.shape or np.any(np.diff(p)<=0):raise ValueError('RR时间轴无效')
    out=np.zeros((len(p),8),np.float32)
    if len(p)<2:return out
    delta=np.r_[0,np.diff(p)].astype(float)
    for i in range(1,len(p)):
        h=delta[max(1,i-32):i];med=np.median(h) if len(h) else delta[i]
        values=delta[max(1,i-7):i+1];out[i,-len(values):]=np.clip(values/med,0,4)/4
    out[~valid]=0
    return out

class FourClassCnn(nn.Module):
    def __init__(self):
        super().__init__();base=create_model(dict(family='residual',feature='both',width=16,input_samples=128))
        def remove_bn(module):
            for name,child in list(module.named_children()):
                if isinstance(child,nn.BatchNorm1d):setattr(module,name,nn.Identity())
                else:remove_bn(child)
        remove_bn(base);self.wave=base.wave;self.rr=base.rr
        self.head=nn.Sequential(nn.Linear(269,64),nn.ReLU(),nn.Dropout(.1),nn.Linear(64,4))
        self.register_buffer('rr_mean',torch.zeros(3));self.register_buffer('rr_std',torch.ones(3))
    def encode(self,x,rr,hand,history_rr):
        r=((rr-self.rr_mean)/self.rr_std).clamp(-5,5)
        wave=self.wave(torch.stack([x,torch.diff(x,dim=-1,prepend=x[:,:1])],1)).flatten(1)
        return torch.cat([wave,self.rr(r),r,hand,history_rr],1)
    def forward(self,x,rr,hand,history_rr):return self.head(self.encode(x,rr,hand,history_rr))

def hand_features(x,rr,background,count):
    values,names=relative_features(x,rr,background,count)
    if values.shape!=(len(x),122):raise ValueError('要求122项固定因果特征')
    return values

def load_model(fold,weights=None):
    if fold not in (0,1,2):raise ValueError('必须指定fold 0/1/2')
    net=FourClassCnn();net.load_state_dict(torch.load(Path(weights) if weights else HERE/f'assets/fold_{fold}.pt',map_location='cpu',weights_only=True));net.eval();return net

def logits(net,x,rr,background,count,history_rr,batch=1024):
    arrays=[np.asarray(v) for v in [x,rr,background,count,history_rr]];x,rr,background,count,history_rr=arrays
    if x.shape!=(len(x),128) or rr.shape!=(len(x),3) or background.shape!=x.shape or count.shape!=(len(x),) or history_rr.shape!=(len(x),8):raise ValueError('模型输入维数不符')
    if not all(np.isfinite(v).all() for v in arrays) or np.any((count<0)|(count>8)):raise ValueError('模型输入非有限/历史计数无效')
    out=[];net.eval()
    with torch.no_grad():
        for i in range(0,len(x),batch):
            sl=slice(i,i+batch);hand=hand_features(x[sl],rr[sl],background[sl],count[sl]);out.extend(net(tensor(x[sl]),tensor(rr[sl]),tensor(hand),tensor(history_rr[sl])).tolist())
    return np.asarray(out,np.float32).reshape(-1,4)

def classify_mv(samples,*,fold,preprocess='hp05',sampling_hz=500):
    """整段记录电脑参考；每次从新记录重建状态，不能逐实时块单独调用。"""
    from scipy.signal import lfilter
    from ecg_model.pipeline import _features
    x=np.asarray(samples,np.float64)
    if sampling_hz!=500 or x.ndim!=1 or not 1<=len(x)<=1800000 or not np.isfinite(x).all():raise ValueError('要求500Hz单路有限mV，1—1800000点')
    if preprocess not in ('raw','hp05'):raise ValueError('preprocess必须为raw或hp05')
    if preprocess=='hp05':
        a=500/(500+2*np.pi*.5);x=lfilter([a,-a],[1,-a],x,zi=[-a*x[0]])[0]
    z=np.copysign(np.floor(np.abs(x*4096)+.5),x);a=_features(np.clip(z,-32768,32767).astype('<i2'))
    # 共用检测/切拍实现，但H27不使用其中的后继RR或HGB分类结果。
    hist=rr_sequence(a['positions500'],a['valid']);pred=np.full(len(hist),-1,np.int64);score=np.full((len(hist),4),np.nan,np.float32);ok=a['valid']
    score[ok]=logits(load_model(fold),a['x'][ok],a['rr'][ok],a['background'][ok],a['history_count'][ok],hist[ok]);pred[ok]=score[ok].argmax(1)
    return dict(positions500=a['positions500'],ready500=a['ready500'],valid=ok,prediction=pred,logits=score,history_rr=hist,clipped_samples=int(np.count_nonzero((z< -32768)|(z>32767))))
