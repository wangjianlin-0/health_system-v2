"""0拟合交接核验；可选全部开发数据重放或新续训结果的独立复核。"""
import argparse,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from network import load_model,logits,torch
from prepare import load,read,sha,write,array_digest
from train import dataset,metric
torch.set_num_threads(4)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--dataset',type=Path);ap.add_argument('--run',type=Path);ap.add_argument('--output',type=Path);args=ap.parse_args();report=dict(passed=True,fit_count=0,test_loaded=False,hardware=False)
    for name,row in read(HERE/'files.json')['files'].items():
        path=(HERE/name).resolve();path.relative_to(HERE)
        if path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:raise ValueError('交接文件SHA/大小不符：'+name)
    for f in range(3):
        z=load(HERE/f'assets/golden_{f}.npz');score=logits(load_model(f),z['x'],z['rr'],z['background'],z['history_count'],z['history_rr']);np.testing.assert_allclose(score,z['logits'],rtol=1e-6,atol=1e-6)
    report['synthetic_vectors']=36
    if args.run and not args.dataset:ap.error('--run需同时指定--dataset')
    if args.dataset:
        p,d,a,events,pair=dataset(args.dataset.resolve());expected=read(HERE/'expected_predictions.json');pooled=np.zeros((4,5),np.int64);extra=np.zeros(4,np.int64);expert=np.zeros((4,5),np.int64);folds=[]
        for f in range(3):
            folder=args.run/f'fold_{f}' if args.run else None;net=load_model(f,folder/'best_weights.pt' if folder else None);vi=np.flatnonzero(np.isin(d['subject'],p['folds'][f]));score=logits(net,d['x'][vi],d['rr'][vi],d['background'][vi],d['history_count'][vi],d['history_rr'][vi]);pred=score.argmax(1);ec=np.zeros((4,5),np.int64);np.add.at(ec,(d['y'][vi],pred),1);expert+=ec
            if folder:
                old=load(folder/'expert_predictions.npz');np.testing.assert_array_equal(pred,old['prediction']);np.testing.assert_allclose(score,old['logits'],rtol=1e-6,atol=1e-6)
            elif array_digest(pred)!=expected[str(f)]['expert_prediction']:raise ValueError('专家预测与H27不符')
            c=np.zeros((4,5),np.int64);ex=np.zeros(4,np.int64);patients={}
            for e in events:
                if e['subject'] not in p['folds'][f]:continue
                ok=e['valid'];score=logits(net,e['x'][ok],e['rr'][ok],e['background'][ok],e['history_count'][ok],e['history_rr'][ok]);pred=np.full(len(ok),-1,np.int64);pred[ok]=score.argmax(1)
                if folder:
                    old=load(folder/(e['record']+'_auto.npz'));np.testing.assert_array_equal(pred,old['prediction']);np.testing.assert_allclose(score,old['logits'],rtol=1e-6,atol=1e-6)
                elif array_digest(pred)!=expected[str(f)]['automatic'][e['record']]:raise ValueError('自动预测与H27不符：'+e['record'])
                # 与续训计数循环独立：用向量索引重算含缺失的混淆矩阵。
                dest=np.full(len(e['ids']),4,np.int64);valid=e['mapped']>=0;j=e['mapped'][valid];dest[valid]=np.where(ok[j],pred[j],4);rc=np.zeros((4,5),np.int64);np.add.at(rc,(d['y'][e['ids']],dest),1);re=np.bincount(pred[e['unmatched']],minlength=4);c+=rc;ex+=re;pc,pe=patients.setdefault(e['subject'],(np.zeros((4,5),np.int64),np.zeros(4,np.int64)));pc+=rc;pe+=re
            met=metric(c,ex);pooled+=c;extra+=ex;folds.append(dict(fold=f,expert=metric(ec,np.zeros(4,np.int64)),automatic=met,patients={s:metric(*v) for s,v in patients.items()}))
            if folder:
                original=read(folder/'result.json');assert original['automatic']==met
            print('VERIFIED_FOLD',f,flush=True)
        report.update(expert=metric(expert,np.zeros(4,np.int64)),automatic=metric(pooled,extra),folds=folds,expert_beats=len(d['y']),automatic_records=len(events))
        if not args.run:
            evidence=read(HERE.parents[1]/'docs/evidence/cnn_fourclass_handoff_20261102.json')['completion'];assert report['automatic']['confusion']==evidence['automatic']['confusion'] and report['automatic']['extra']==evidence['automatic']['extra']
    if args.output:write(args.output,report)
    print(json.dumps({k:v for k,v in report.items() if k!='folds'},ensure_ascii=False))
if __name__=='__main__':main()
