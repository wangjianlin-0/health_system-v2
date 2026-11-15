"""把已完成的历史形态与当前拍显式比较；不识别R峰或使用类别。"""
from collections import deque
import numpy as np
from .ecg_features import extract_features


def aligned(x):
    x=np.asarray(x,dtype=np.float32)
    if x.shape[-1]!=128 or not np.isfinite(x).all():raise ValueError('波形无效')
    peak=np.argmax(np.abs(x[...,44:60]),axis=-1)+44
    value=np.take_along_axis(x,peak[...,None],axis=-1)[...,0]
    return x*np.where(value<0,-1.,1.)[...,None]


class CompletedHistory:
    """当前R时刻仅释放last_sample<=R的窗口；记录边界重建实例。"""
    def __init__(self,capacity=8):
        if capacity<1:raise ValueError('容量无效')
        self.pending=deque();self.ready=deque(maxlen=capacity);self.previous=None

    def at_r(self,position):
        position=int(position)
        if self.previous is not None and position<=self.previous:raise ValueError('R位置不递增')
        self.previous=position
        while self.pending and self.pending[0][0]<=position:self.ready.append(self.pending.popleft())
        if not self.ready:return np.zeros(128,dtype=np.float32),0,-1
        template=np.median(np.stack([row[1] for row in self.ready]),axis=0).astype(np.float32)
        return template,len(self.ready),int(self.ready[-1][0])

    def enqueue(self,last_sample,x):
        last_sample=int(last_sample)
        if self.previous is None or last_sample<=self.previous:raise ValueError('当前窗口结束位置无效')
        if self.pending and last_sample<=self.pending[-1][0]:raise ValueError('窗口结束位置不递增')
        self.pending.append((last_sample,aligned(x).astype(np.float32).copy()))


def relative_features(x,rr,template,count):
    base,names=extract_features(x,rr)
    z=aligned(x).astype(np.float64);b=np.asarray(template,dtype=np.float64);count=np.asarray(count)
    if b.shape!=z.shape or count.shape!=(len(z),) or np.any((count<0)|(count>8)) or not np.isfinite(b).all():
        raise ValueError('背景形状/数量无效')
    delta=z-b;extra=[delta.reshape(-1,32,4).mean(2)]
    labels=[f'rel_mean4_{i}' for i in range(32)]
    for name,lo,hi in [('pre',8,40),('qrs',40,66),('post',66,104),('tail',104,128)]:
        d=delta[:,lo:hi]
        extra.append(np.stack([np.mean(np.abs(d),1),np.mean(d,1),np.mean(d*d,1)],axis=1))
        labels.extend(f'rel_{name}_{s}' for s in ['absolute','mean','energy'])
    def cosine(lo,hi):
        a=z[:,lo:hi];t=b[:,lo:hi]
        return np.sum(a*t,1)/np.maximum(np.sqrt(np.sum(a*a,1)*np.sum(t*t,1)),1e-8)
    ratio=np.mean(z[:,40:66]**2,1)/np.maximum(np.mean(b[:,40:66]**2,1),1e-4)
    ratio=np.where(count>0,np.clip(ratio,0,8),0)
    extra.append(np.stack([cosine(0,128),cosine(40,66),count/8.,ratio],axis=1))
    labels+=['rel_cosine','rel_qrs_cosine','history_count_fraction','rel_qrs_energy_ratio']
    values=np.concatenate([base,*extra],axis=1).astype(np.float32)
    if not np.isfinite(values).all():raise ValueError('非有限相对特征')
    return values,names+labels
