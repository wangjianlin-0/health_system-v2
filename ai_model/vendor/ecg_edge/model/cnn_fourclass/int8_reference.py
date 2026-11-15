"""H27动态W8A8参考：逐层/逐拍二次幂缩放，INT32 MAC，FP32层间及偏置。

无需患者校准或训练；它是混合精度量化，不声称全整数网络。
"""
import numpy as np


def quantize(values, axis=None):
    x = np.asarray(values, np.float32)
    maximum = np.max(np.abs(x), axis=axis, keepdims=axis is not None)
    # 允许零张量，固定2^-24下限；所有舍入均为最近、半值远离零。
    exponent = np.maximum(-24, np.ceil(np.log2(np.maximum(maximum / 127, 2.**-24))))
    scale = np.exp2(exponent).astype(np.float32)
    v = x / scale
    q = np.clip(np.copysign(np.floor(np.abs(v) + np.float32(.5)), v), -127, 127).astype(np.int8)
    return q, scale


class Int8Reference:
    def __init__(self, state):
        self.state = {k:np.asarray(v, np.float32) for k,v in state.items()}
        self.weights = {}
        for name,w in self.state.items():
            if name.endswith('.weight'):
                self.weights[name] = quantize(w, tuple(range(1,w.ndim)))

    def conv(self, x, name):
        q,s = quantize(x);w,ws = self.weights[name]
        length=x.shape[1];kernel=w.shape[-1]
        padded=np.pad(q,((0,0),(kernel//2,kernel//2)))
        windows=np.lib.stride_tricks.sliding_window_view(padded,kernel,axis=1)
        acc=np.einsum('itk,oik->ot',windows.astype(np.int32),w.astype(np.int32),optimize=False)
        return acc.astype(np.float32)*(s*ws.reshape(-1,1))

    def dense(self,x,name,relu):
        q,s=quantize(x);w,ws=self.weights[name+'.weight']
        acc=w.astype(np.int32)@q.astype(np.int32)
        y=acc.astype(np.float32)*(s*ws.reshape(-1))+self.state[name+'.bias']
        return np.maximum(y,0) if relu else y

    def forward(self,packed,trace=False):
        v=np.asarray(packed,np.float32)
        if v.shape!=(261,) or not np.isfinite(v).all():raise ValueError('要求261项有限FP32输入')
        x=np.stack([v[:128],np.r_[np.float32(0),np.diff(v[:128])]])
        layers={}
        x=np.maximum(self.conv(x,'wave.0.weight'),0);layers['stem']=x.copy()
        for block in (3,4,5):
            b=np.maximum(self.conv(x,f'wave.{block}.body.0.weight'),0)
            c=self.conv(b,f'wave.{block}.body.3.weight')
            x=np.maximum(x+c,0).reshape(16,-1,2).max(2);layers[f'block{block}']=x.copy()
        wave=x.reshape(16,8,2).max(2).reshape(-1)
        r=np.clip((v[128:131]-self.state['rr_mean'])/self.state['rr_std'],-5,5)
        features=np.r_[wave,self.dense(r,'rr.0',True),r,v[131:253],v[253:261]].astype(np.float32)
        hidden=self.dense(features,'head.0',True);out=self.dense(hidden,'head.3',False)
        layers.update(features=features,hidden=hidden,logits=out)
        return (out,layers) if trace else out
