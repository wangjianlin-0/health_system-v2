"""四层不下采样Haar差分绝对均值；当前/已完成背景及限幅比值。"""
import numpy as np


def band_values(x):
    low=np.asarray(x,np.float64)
    if low.ndim!=2 or low.shape[1]!=128 or not np.isfinite(low).all():raise ValueError('频带窗口无效')
    values=[]
    for distance in [1,2,4,8]:
        delayed=np.concatenate([np.repeat(low[:,:1],distance,axis=1),low[:,:-distance]],axis=1)
        detail=(low-delayed)/2;low=(low+delayed)/2
        for lo,hi in [(16,40),(40,80),(80,120)]:values.append(np.mean(np.abs(detail[:,lo:hi]),axis=1))
    return np.stack(values,axis=1)


def band_features(x,background,count):
    x=np.asarray(x);background=np.asarray(background);count=np.asarray(count)
    if x.shape!=background.shape or count.shape!=(len(x),) or np.any((count<0)|(count>8)):raise ValueError('频带背景无效')
    current=band_values(x);past=band_values(background);ratio=np.clip(current/np.maximum(past,.01),0,8);ratio[count==0]=0
    values=np.c_[current,past,ratio].astype(np.float32)
    names=[f'band_{kind}_level{level}_{region}' for kind in ['current','completed_background','ratio_floor01'] for level in range(1,5) for region in ['pre','qrs','post']]
    return values,names
