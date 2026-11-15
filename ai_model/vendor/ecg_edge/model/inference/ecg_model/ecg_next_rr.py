"""有界等待实际下一事件报告，超时新增节律置零；不接收标签。"""
import numpy as np
FEATURE_NAMES=['next_seconds_div4','next_pre_ratio_div8','next_past80_div4','next_past400_div4','pair_past80_div4','next_pre_asymmetry','next_available']
def next_rr(position,reported,samples,eligible=None,maximum_wait=1250):
    position=np.asarray(position,np.int64);reported=np.asarray(reported,np.int64);n=len(position)
    if position.ndim!=1 or reported.shape!=position.shape or samples<1 or maximum_wait<1:raise ValueError('时间轴无效')
    eligible=np.ones(n,bool) if eligible is None else np.asarray(eligible,bool)
    if eligible.shape!=(n,):raise ValueError('资格形状无效')
    # 少数公开标注含记录开始前的负索引；只保留为无效历史上下文，不作可分类事件。
    if np.any(np.diff(position)<=0) or np.any(np.diff(reported)<0) or np.any((position<0)&eligible) or np.any(reported<0) or np.any(reported<position) or np.any(reported>=samples):raise ValueError('事件顺序/报告范围无效')
    pre=np.r_[0,np.diff(position)] if n else np.array([],np.int64);past80=np.zeros(n);past400=np.zeros(n)
    for i in range(1,n):
        h=pre[max(1,i-400):i];past400[i]=np.mean(h) if len(h) else pre[i];h=pre[max(1,i-80):i];past80[i]=np.mean(h) if len(h) else pre[i]
    following=np.r_[position[1:],-1] if n else np.array([],np.int64);report_next=np.r_[reported[1:],samples] if n else np.array([],np.int64);deadline=np.minimum(position+maximum_wait,samples-1)
    available=eligible&(pre>0)&(following>position)&(following-position<=maximum_wait)&(report_next<=deadline)
    decision=np.where(available,np.maximum(reported,report_next),np.maximum(reported,deadline));decision=np.where(eligible&(pre>0),decision,reported)
    extra=np.zeros((n,7),np.float32);ix=np.flatnonzero(available)
    if len(ix):
        a=pre[ix].astype(float);b=(following[ix]-position[ix]).astype(float);local=past80[ix];long=past400[ix]
        extra[ix]=np.c_[np.clip(b/500,0,4)/4,np.clip(b/a,0,8)/8,np.clip(b/local,0,4)/4,np.clip(b/long,0,4)/4,np.clip((a+b)/(2*local),0,4)/4,(b-a)/(b+a),np.ones(len(ix))].astype(np.float32)
    return dict(extra=extra,available=available,decision_at=decision,base_ready=reported.copy())
