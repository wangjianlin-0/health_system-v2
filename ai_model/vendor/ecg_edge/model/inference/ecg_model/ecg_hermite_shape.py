"""固定近R37点六方向Hermite投影；只读当前窗及原已完成中位背景。"""
import numpy as np
FEATURE_NAMES=[f'hermite_current_{i}' for i in range(6)]+[f'hermite_background_delta_{i}' for i in range(6)]+['hermite_current_residual_fraction','hermite_delta_residual_fraction']

def hermite_features(x,background,count,valid,basis):
    x=np.asarray(x,np.float32);background=np.asarray(background,np.float32);count=np.asarray(count);valid=np.asarray(valid);basis=np.asarray(basis,np.float32)
    if x.ndim!=2 or x.shape[1]!=128 or background.shape!=x.shape or count.shape!=(len(x),) or valid.shape!=(len(x),) or valid.dtype.kind!='b' or count.dtype.kind not in 'iu' or np.any(count<0) or np.any(count>8) or basis.shape!=(37,6):raise ValueError('Hermite输入形状/状态错误')
    if not np.isfinite(x).all() or not np.isfinite(background).all() or not np.isfinite(basis).all():raise ValueError('非有限Hermite输入')
    peak=np.argmax(np.abs(x[:,44:60]),axis=1)+44;z=x.astype(np.float64)*np.where(x[np.arange(len(x)),peak]<0,-1.,1.)[:,None]
    fraction=(np.arange(33,70)-31.5)/45.;b=background.astype(np.float64)
    a=z[:,33:70]-(z[:,28:36].mean(1)[:,None]*(1-fraction)+z[:,73:81].mean(1)[:,None]*fraction)
    bb=b[:,33:70]-(b[:,28:36].mean(1)[:,None]*(1-fraction)+b[:,73:81].mean(1)[:,None]*fraction);delta=a-bb
    ac=np.zeros((len(x),6),np.float64);dc=np.zeros_like(ac)
    for j in range(37):ac+=a[:,j,None]*basis[j].astype(np.float64);dc+=delta[:,j,None]*basis[j].astype(np.float64)
    ae=np.sum(a*a,1);be=np.sum(bb*bb,1);de=np.sum(delta*delta,1)
    extra=np.c_[ac/np.sqrt(ae[:,None]+1e-8),dc/np.sqrt((ae+be)[:,None]+1e-8),np.maximum(ae-np.sum(ac*ac,1),0)/(ae+1e-8),np.maximum(de-np.sum(dc*dc,1),0)/(ae+be+1e-8)].astype(np.float32)
    extra[count==0,6:12]=0;extra[count==0,13]=0;extra[~valid]=0
    if not np.isfinite(extra).all():raise ValueError('Hermite结果非有限')
    return extra
