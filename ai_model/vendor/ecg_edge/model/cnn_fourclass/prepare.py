"""0拟合数据准备：导入已核缓存，或从允许的公开原始记录重建。"""
import argparse,hashlib,json,math,sys,shutil
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'model/prepare'),str(ROOT/'model/inference')]
from features import rr_sequence
from prepare_cnn_git import array_digest,validate_protocol

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):
    with np.load(p,allow_pickle=False) as z:return dict(z)
def write(p,z):Path(p).write_text(json.dumps(z,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def check_fields(values,expected):
    for k,h in expected.items():
        if k not in values or array_digest(values[k])!=h:raise ValueError('字段未精确复现：'+k)

def import_cache(original,out):
    """可选本机快捷路径；不把此路径写成队友运行依赖。"""
    expected=read(HERE/'expected_inputs.json');rows=[]
    for role in ['development','auxiliary']:
        z=load(original/f'tmp/cnn_git/cache/{role}.npz');b=load(original/f'tmp/ecg_relative_cache_v5_20261024_01/{role}.npz');q=load(original/f'tmp/ecg_rr_sequence_cache_v80_20261028_01/{role}.npz')
        for k in ['record','subject','r_index']:np.testing.assert_array_equal(z[k],b[k]);np.testing.assert_array_equal(z[k],q[k])
        z.update(background=b['background'],history_count=b['history_count'],last_history_sample=b['last_history_sample'],history_rr=q['extra']);check_fields(z,expected['roles'][role]);np.savez_compressed(out/(role+'.npz'),**z)
    root=original/'tmp/ecg_energy_inputs_cache_v91_20261029_01'
    for row in read(root/'manifest.json')['records']:
        if row['mode']!='hp05':continue
        z=load(root/row['npz'].replace('\\','/'));z['history_rr']=rr_sequence(z['positions500'],z['valid']);meta={k:row[k] for k in ['record','subject','fs']};check_fields(z,expected['automatic'][row['record']]['fields']);np.savez_compressed(out/'automatic'/(row['record']+'.npz'),**z);rows.append(meta)
    return rows

def raw_record(row,raw,protocol):
    import wfdb
    stem=raw/row['database']/row['record']
    for ext in ['dat','hea','atr']:
        path=stem.with_suffix('.'+ext)
        if sha(path)!=protocol['raw_sha256'][row['database']+'/'+path.name]:raise ValueError('原始文件SHA不符：'+str(path))
    h=wfdb.rdheader(str(stem));ch=h.sig_name.index(row['lead'])
    if h.fs!=row['fs'] or h.units[ch]!='mV' or h.adc_gain[ch]<=0:raise ValueError('导联/单位/采样率不符')
    digital=wfdb.rdrecord(str(stem),channels=[ch],physical=False).d_signal[:,0]
    if int(digital[0])!=h.init_value[ch] or (int(digital.astype(np.int64).sum())-h.checksum[ch])%65536:raise ValueError('WFDB校验不符')
    if row['database']=='incartdb' and 'patient '+row['subject'].split(':')[1] not in h.comments:raise ValueError('患者身份不符')
    return (digital.astype(np.float64)-h.baseline[ch])/h.adc_gain[ch],h,wfdb.rdann(str(stem),'atr')

def rebuild(raw,base,out,smoke_record=None):
    from prepare_cnn_expanded import BEATS,common_window
    from ecg_model.ecg_relative_features import CompletedHistory
    from ecg_model.pipeline import _features
    from scipy.signal import resample_poly,lfilter
    p=read(ROOT/'model/protocols/cnn_git_v1_protocol.json');validate_protocol(p);expected=read(HERE/'expected_inputs.json');rows=[]
    for role in ['development','auxiliary']:
        z=load(base/(role+'.npz'))
        if {k:array_digest(v) for k,v in z.items()}!=p['expected_array_sha256'][role]:raise ValueError('基础输入未逐值复现冻结数据')
        background=np.zeros_like(z['x']);count=np.zeros(len(z['y']),np.int8);ends=np.full(len(z['y']),-1,np.int64);hist=np.zeros((len(z['y']),8),np.float32);seen=np.zeros(len(z['y']),bool)
        for row in p[role+'_records']:
            key=row['database']+':'+row['record']
            if smoke_record and key!=smoke_record:continue
            mv,h,ann=raw_record(row,raw,p);keep=np.array([s in BEATS for s in ann.symbol]);native=ann.sample[keep].astype(np.int64);pos500=(native*500+int(h.fs)//2)//int(h.fs);full_rr=rr_sequence(pos500,np.ones(len(native),bool));lookup={int(v):i for i,v in enumerate(native)};ids=np.flatnonzero(z['record']==key);targets={int(z['r_index'][i]):int(i) for i in ids};state=CompletedHistory(8);after=math.ceil(h.fs*p['window']['after_seconds'])
            for pos in native:
                pos=int(pos);bg,c,end=state.at_r(pos);current=common_window(mv,pos,h.fs,p['window'])
                if pos in targets:
                    i=targets[pos];np.testing.assert_array_equal(current,z['x'][i]);background[i]=bg;count[i]=c;ends[i]=end;hist[i]=full_rr[lookup[pos]];seen[i]=True
                if current is not None:state.enqueue(pos+after-1,current)
            if not seen[ids].all():raise ValueError('未覆盖目标心拍')
            if role=='development':
                source=resample_poly(mv,500,int(h.fs));a=500/(500+2*np.pi*.5);filtered=lfilter([a,-a],[1,-a],source,zi=[-a*source[0]])[0];code=np.copysign(np.floor(np.abs(filtered*4096)+.5),filtered);auto=_features(np.clip(code,-32768,32767).astype('<i2'));ref=np.array([s in BEATS for s in ann.symbol]);auto.update(reference_indices=ann.sample[ref].astype(np.int64),reference_symbols=np.asarray(ann.symbol)[ref],history_rr=rr_sequence(auto['positions500'],auto['valid']));check_fields(auto,expected['automatic'][row['record']]['fields']);np.savez_compressed(out/'automatic'/(row['record']+'.npz'),**auto);rows.append({k:row[k] for k in ['record','subject','fs']})
            print('PREPARED',key,flush=True)
        z.update(background=background,history_count=count,last_history_sample=ends,history_rr=hist)
        if smoke_record:
            z={k:v[seen] for k,v in z.items()}
        else:
            if not seen.all():raise ValueError('重建缺心拍')
            check_fields(z,expected['roles'][role])
        np.savez_compressed(out/(role+'.npz'),**z)
    return rows

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=['import-cache','rebuild']);ap.add_argument('--original-root',type=Path);ap.add_argument('--raw-dir',type=Path);ap.add_argument('--base-cache',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--smoke-record');a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'automatic').mkdir()
    if a.mode=='import-cache':
        if not a.original_root:ap.error('import-cache需要--original-root')
        rows=import_cache(a.original_root.resolve(),out)
    else:
        if not a.raw_dir or not a.base_cache:ap.error('rebuild需要--raw-dir和--base-cache')
        rows=rebuild(a.raw_dir.resolve(),a.base_cache.resolve(),out,a.smoke_record)
    p=read(ROOT/'model/protocols/cnn_git_v1_protocol.json')
    if not a.smoke_record and (len(rows)!=61 or {r['subject'] for r in rows}!={s for f in p['folds'] for s in f}):raise ValueError('自动记录/患者覆盖不完整')
    files={str(v.relative_to(out)).replace('\\','/'):sha(v) for v in out.rglob('*.npz')};write(out/'manifest.json',dict(complete=not bool(a.smoke_record),files=files,automatic=rows,test_loaded=False,protocol_sha256=sha(HERE/'protocol.json')));print('PREPARE_COMPLETE',not bool(a.smoke_record))
if __name__=='__main__':main()
