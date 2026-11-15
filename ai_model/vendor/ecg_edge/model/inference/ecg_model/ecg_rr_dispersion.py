"""仅当前及此前R事件的12维节律；不是临床HRV或NN间期测量。"""
import numpy as np

FEATURE_NAMES=['rr_current_previous_div4','rr_previous_median8_div4',
 'rr_current_median8_div4','rr_current_median32_div4',
 'rr_past8_cv_div2','rr_past32_cv_div2',
 'rr_past8_rmssd_mean_div2','rr_past32_rmssd_mean_div2',
 'rr_current_lag2_error_median8_div4','rr_adjacent_asymmetry',
 'rr_mean8_mean32_div4','rr_history_count32_fraction']

def rr_dispersion(positions):
    original=np.asarray(positions)
    if original.ndim!=1 or (len(original) and original.dtype.kind not in 'iu'):
        raise ValueError('R位置必须是一维整数')
    if len(original) and np.any(np.abs(original.astype(float))>2**52):raise ValueError('R位置超出精确范围')
    p=original.astype(np.int64);n=len(p)
    if np.any(np.diff(p)<=0):raise ValueError('R位置必须严格递增')
    result=np.zeros((n,12),np.float32)
    if n<2:return result
    pre=np.r_[0,np.diff(p)].astype(float)
    # 每行只含当前间隔之前最多32个间隔；前两R尚无更早间隔。
    h=np.lib.stride_tricks.sliding_window_view(np.r_[np.full(33,np.nan),pre[1:-1]],32)
    stats=[]
    for size in [8,32]:
        a=h[:,-size:];count=np.sum(np.isfinite(a),axis=1)
        mean=np.divide(np.nansum(a,axis=1),count,out=pre.copy(),where=count>0)
        median=pre.copy();have=count>0;median[have]=np.nanmedian(a[have],axis=1)
        sd=np.sqrt(np.divide(np.nansum((a-mean[:,None])**2,axis=1),count,out=np.zeros(n),where=count>0))
        delta=np.diff(a,axis=1);dc=np.sum(np.isfinite(delta),axis=1)
        rmssd=np.sqrt(np.divide(np.nansum(delta**2,axis=1),dc,out=np.zeros(n),where=dc>0))
        stats.append((mean,median,sd,rmssd,count))
    m8,med8,sd8,rm8,c8=stats[0];m32,med32,sd32,rm32,c32=stats[1]
    previous=np.r_[0,pre[:-1]];previous=np.where(c32>0,previous,pre)
    lag2=np.r_[0,0,pre[:-2]];lag2=np.where(c32>=2,lag2,pre)
    def ratio(a,b,limit):return np.clip(np.divide(a,b,out=np.zeros(n),where=b>0),0,limit)/limit
    result[:]=np.c_[ratio(pre,previous,4),ratio(previous,med8,4),ratio(pre,med8,4),ratio(pre,med32,4),
        ratio(sd8,m8,2),ratio(sd32,m32,2),ratio(rm8,m8,2),ratio(rm32,m32,2),
        ratio(abs(pre-lag2),med8,4),np.divide(pre-previous,pre+previous,out=np.zeros(n),where=pre+previous>0),
        ratio(m8,m32,4),c32/32]
    result[0]=0
    if not np.isfinite(result).all():raise ValueError('非有限节律')
    return result
