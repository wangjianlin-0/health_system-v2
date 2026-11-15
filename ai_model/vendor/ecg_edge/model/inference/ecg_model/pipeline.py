"""冻结v91自动输入及v92树参数；记录之间重新建立全部检测/历史状态。"""
from pathlib import Path
import json,os,struct,subprocess
import numpy as np
from scipy.signal import lfilter,upfirdn
from .ecg_relative_features import aligned,relative_features
from .ecg_band_features import band_features
from .ecg_next_rr import next_rr,FEATURE_NAMES as NEXT_NAMES
from .ecg_rr_dispersion import rr_dispersion,FEATURE_NAMES as RHYTHM_NAMES
from .ecg_hermite_shape import hermite_features,FEATURE_NAMES as HERMITE_NAMES
from .tree_model import probability

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
for _key,_value in dict(sampling_hz=500,input_unit='mV',maximum_samples=1800000,
    maximum_wait_ticks=1250,source_codes_per_mV=4096,highpass_hz=.5,
    window_before=178,window_after=267,model_points=128,features=192,
    classes=['N','S','VF'],model_version='v92').items():
    if CONFIG.get(_key)!=_value:raise ValueError('冻结模型配置不匹配，不能单改配置冒充兼容：'+_key)
DT=np.dtype([('generation','<u4'),('beat_id','<u4'),('position','<u4'),
 ('rr_samples','<u4'),('sampling_hz','<u4'),('ready_at','<u4'),
 ('input_status','<u4'),('waveform','<f4',(128,)),('rr','<f4',(3,))])

def _native(name,payload):
    exe=ROOT/'bin'/(name+('.exe' if os.name=='nt' else ''))
    if not exe.is_file():raise RuntimeError('缺少主机程序，请先运行build_native.py --cc <gcc路径>：'+str(exe))
    q=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=120,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=ROOT)
    if q.returncode or len(q.stdout)%DT.itemsize:
        raise RuntimeError(f'{name}失败，返回{q.returncode}：'+q.stderr.decode('utf-8',errors='replace'))
    return np.frombuffer(q.stdout,DT).copy()

def _energy_center(codes,requests):
    p=requests['position'].astype(np.int64);ready=requests['ready_at'].astype(np.int64)
    m=(p*18+12)//25+20
    taps=np.array(json.loads((ROOT/'assets/detector_fir.json').read_text(encoding='utf-8')))
    length=(len(codes)-1)*18//25+1
    raw=upfirdn(taps,codes.astype(np.float64),up=18,down=25)[:length]
    signal=np.clip(np.copysign(np.floor(np.abs(raw)+.5),raw),-32768,32767).astype(np.int16)
    safe=(m>=36)&(m+36<length)&(((m+36)*25+17)//18<=ready)
    ix=np.flatnonzero(safe);w=signal[m[ix,None]+np.arange(-36,37)]
    d=np.diff(w.astype(np.int64),axis=1);weight=d*d
    mass=weight.sum(1);moment=weight@np.arange(-71,72,2,dtype=np.int64)
    ix=ix[mass>0];moment=moment[mass>0];mass=mass[mass>0]
    mid=(2*m[ix]*mass+moment+mass)//(2*mass)
    new=p.copy();new[ix]=((mid-20)*25+9)//18
    if np.any(np.diff(new)<=0):raise RuntimeError('能量定位后事件次序异常；不自动排序/删拍')
    complete=(new>=178)&(new+266<len(codes))
    ready=np.maximum.accumulate(np.maximum(ready,np.where(complete,new+266,ready)))
    if np.any(ready>=len(codes)):raise RuntimeError('报告时刻超过记录末尾')
    return new,ready,complete

def _features(codes):
    original=_native('detector500',codes.tobytes())
    position,ready,complete=_energy_center(codes,original)
    payload=struct.pack('<II',len(codes),len(position))+codes.tobytes()+np.c_[position,ready].astype('<u4').tobytes()
    requests=_native('recut500',payload);n=len(requests)
    if n!=len(position):raise RuntimeError('重切事件数不符')
    np.testing.assert_array_equal(requests['position'],position)
    np.testing.assert_array_equal(requests['ready_at'],ready)
    expected_status=np.where(~complete,4,np.where(np.arange(n)==0,2,0))
    np.testing.assert_array_equal(requests['input_status'],expected_status)
    x=requests['waveform'].copy();rr=requests['rr'].copy();valid=requests['input_status']==0
    background=np.zeros_like(x);count=np.zeros(n,np.int8);last=np.full(n,-1,np.int64)
    ids=np.flatnonzero(complete);reported=ready[ids]
    for i,pos in enumerate(position):
        at=np.searchsorted(reported,pos,side='right');history=ids[max(0,at-8):at]
        if len(history):
            if history[-1]>=i:raise RuntimeError('历史包含当前或未来事件')
            background[i]=np.median(aligned(x[history]),axis=0).astype(np.float32)
            count[i]=len(history);last[i]=ready[history[-1]]
    base=np.zeros((n,159),np.float32);pre=requests['rr_samples'].astype(float)/500
    # 空矩阵调用也生成精确的特征名称顺序。
    rel,names=relative_features(x[valid],rr[valid],background[valid],count[valid])
    band,band_names=band_features(x[valid],background[valid],count[valid])
    base[valid]=np.c_[rel,(np.clip(pre[valid],0,4)/4).astype(np.float32),band]
    following=next_rr(position,ready,len(codes),valid,1250)
    with np.load(ROOT/'assets/hermite_basis.npz',allow_pickle=False) as z:basis=z['basis']
    hermite=hermite_features(x,background,count,valid,basis)
    features=np.c_[base,following['extra'],rr_dispersion(position),hermite]
    all_names=names+['pre_seconds_div4']+band_names+NEXT_NAMES+RHYTHM_NAMES+HERMITE_NAMES
    frozen_names=json.loads((ROOT/'assets/feature_names.json').read_text(encoding='utf-8'))
    if all_names!=frozen_names:raise RuntimeError('192项特征名称或顺序与权重不一致')
    if features.shape!=(n,192) or not np.isfinite(features).all():raise RuntimeError('特征数量/数值错误')
    return dict(requests=requests,original_requests=original,features=features,x=x,rr=rr,
        pre=pre,positions500=position,ready500=ready,status=requests['input_status'],valid=valid,
        complete=complete,background=background,history_count=count,last_history_sample500=last,
        next_available=following['available'],decision_at=following['decision_at'])

def infer_codes(codes,*,fold):
    """内部回放接口：已按模型标度量化的int16，500Hz，不再滤波。

    4096 codes/mV仅是模型回放约定，不是ADS1292R的原始ADC转换。
    每次调用是一条完整连续记录；不能把实时分块逐次独立调用。
    """
    a=np.asarray(codes)
    if a.ndim!=1 or a.dtype.kind!='i' or a.dtype.itemsize!=2 or not 1<=len(a)<=1800000:
        raise ValueError('要求1—1800000个连续int16模型码值')
    if isinstance(fold,bool) or fold not in (0,1,2):raise ValueError('必须明确选择研究模型fold=0/1/2')
    result=_features(a.astype('<i2',copy=False));valid=result['valid']
    probs=np.full((len(valid),3),np.nan);classes=np.full(len(valid),-1,np.int32)
    with np.load(ROOT/f'assets/v92_fold{fold}.npz',allow_pickle=False) as model:
        np.testing.assert_array_equal(model['classes'],[0,1,2])
        if valid.any():
            probs[valid]=probability(result['features'][valid],model)
            classes[valid]=probs[valid].argmax(1)
    labels=np.full(len(valid),'UNCLASSIFIED',dtype='<U12');labels[valid]=np.array(['N','S','VF'])[classes[valid]]
    result.update(probabilities=probs,class_id=classes,labels=labels,fold=np.array(fold))
    return result

def infer_mv(samples,*,fold,preprocess,sampling_hz=500):
    """单路mV入口；hp05为匹配研究评价的因果0.5Hz一阶高通，raw不加此高通。"""
    x=np.asarray(samples,dtype=np.float64)
    if sampling_hz!=500:raise ValueError('仅接受500Hz；不得只改采样率标记冒充重采样')
    if x.ndim!=1 or not 1<=len(x)<=1800000 or not np.isfinite(x).all():raise ValueError('要求有限、连续、单导联mV数组')
    if preprocess not in ('raw','hp05'):raise ValueError('preprocess必须明确为raw或hp05')
    if preprocess=='hp05':
        a=500/(500+2*np.pi*.5);x=lfilter([a,-a],[1,-a],x,zi=[-a*x[0]])[0]
    codes=np.copysign(np.floor(np.abs(x*4096)+.5),x)
    clipped=int(np.count_nonzero((codes< -32768)|(codes>32767)))
    result=infer_codes(np.clip(codes,-32768,32767).astype('<i2'),fold=fold)
    result.update(clipped_samples=np.array(clipped),source_samples=np.array(len(x)),preprocess=np.array(preprocess))
    return result
