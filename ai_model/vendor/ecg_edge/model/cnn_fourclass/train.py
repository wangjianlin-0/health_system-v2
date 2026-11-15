"""H27便携续训入口。默认只预检，显式--train才拟合；不读取独立测试。"""
import os
for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ.setdefault(key,'4')
import argparse,hashlib,json,time,sys
from pathlib import Path
import numpy as np
import torch
from torch import nn
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
from network import load_model,tensor,hand_features,logits
from prepare import load,read,write,sha
torch.set_num_threads(4)

def metric(c,extra):
    tp=np.diag(c[:,:4]);support=c.sum(1);pred=c[:,:4].sum(0)+extra;p=np.divide(tp,pred,out=np.zeros(4,float),where=pred>0);r=np.divide(tp,support,out=np.zeros(4,float),where=support>0);f=np.divide(2*p*r,p+r,out=np.zeros(4,float),where=p+r>0)
    return dict(confusion=c.tolist(),extra=extra.tolist(),support=support.tolist(),precision=p.tolist(),recall=r.tolist(),f1=f.tolist(),macro_f1=float(f.mean()),priority_f1=float(f[:3].mean()),accuracy=float(tp.sum()/max(1,support.sum())))

def matching(ref,det,tolerance):
    out={};used=set();j=0
    for t in ref:
        while j<len(det) and det[j]<t-tolerance:j+=1
        if j<len(det) and det[j]<=t+tolerance:out[int(t)]=j;used.add(j);j+=1
    return out,used

def dataset(root):
    p=read(HERE/'protocol.json');m=read(root/'manifest.json')
    if not m['complete'] or m['test_loaded'] or m['protocol_sha256']!=sha(HERE/'protocol.json'):raise ValueError('缓存不完整/协议不符')
    for name,h in m['files'].items():
        path=(root/name).resolve();path.relative_to(root.resolve())
        if sha(path)!=h:raise ValueError('缓存SHA不符：'+name)
    d=load(root/'development.npz');a=load(root/'auxiliary.npz');allowed={s for f in p['folds'] for s in f};excluded=set(p['excluded'])
    if set(d['subject'])!=allowed or (set(d['subject'])|set(a['subject']))&excluded:raise ValueError('患者隔离不符')
    events=[];pair={}
    for meta in m['automatic']:
        e=load(root/'automatic'/(meta['record']+'.npz'));e.update(meta);ids=np.flatnonzero(d['record']=='incartdb:'+meta['record']);assoc,used=matching(e['reference_indices']*500,e['positions500']*meta['fs'],round(.05*500*meta['fs']));mapped=np.array([assoc.get(int(d['r_index'][i])*500,-1) for i in ids],np.int64);e.update(ids=ids,mapped=mapped,unmatched=np.array([j for j in range(len(e['valid'])) if j not in used and e['valid'][j]],np.int64));events.append(e)
        for i,j in zip(ids,mapped):
            if j>=0 and e['valid'][j]:pair[int(i)]=(e,int(j))
    return p,d,a,events,pair

FIELDS=['x','rr','background','history_count','history_rr']
def split(p,d,a,events,pair,f):
    held=set(p['folds'][f]);chosen=[];importance={}
    for subject in sorted(set(d['subject'])-held):
        for cls,cap in enumerate(p['train_sampling']['per_verified_subject_per_class']):
            ids=np.flatnonzero((d['subject']==subject)&(d['y']==cls));ids=sorted(ids,key=lambda i:hashlib.sha256(f"{p['train_sampling']['seed']}:{d['record'][i]}:{d['r_index'][i]}".encode()).digest());take=ids[:cap];chosen+=take
            for i in take:importance[int(i)]=len(ids)/len(take)
    ids=np.array(sorted(chosen),np.int64);paired=np.array([i for i in ids if int(i) in pair],np.int64);z={}
    for key in FIELDS:z[key]=np.concatenate([d[key][ids],a[key],np.asarray([pair[int(i)][0][key][pair[int(i)][1]] for i in paired])])
    y=np.r_[d['y'][ids],a['y'],d['y'][paired]].astype(np.int64);mass=np.r_[[importance[int(i)]*(.5 if int(i) in pair else 1.) for i in ids],np.ones(len(a['y'])),[importance[int(i)]*.5 for i in paired]].astype(np.float32)
    subjects=set(d['subject'][ids])|set(a['subject'])
    if subjects&(held|set(p['excluded'])):raise ValueError('训练患者泄漏')
    if abs(float(mass.sum())-(np.sum(~np.isin(d['subject'],list(held)))+len(a['y'])))>.1:raise ValueError('原拍质量未守恒')
    return z,y,mass,dict(train_subjects=sorted(subjects),validation_subjects=sorted(held),rows=len(y),indices_sha256=hashlib.sha256(ids.tobytes()).hexdigest())


def encode(net,z,batch=1024):
    out=[];net.eval()
    with torch.no_grad():
        for i in range(0,len(z['x']),batch):
            sl=slice(i,i+batch);hand=hand_features(z['x'][sl],z['rr'][sl],z['background'][sl],z['history_count'][sl]);out.append(net.encode(tensor(z['x'][sl]),tensor(z['rr'][sl]),tensor(hand),tensor(z['history_rr'][sl])))
    return torch.cat(out)

def automatic(net,cached,d):
    c=np.zeros((4,5),np.int64);extra=np.zeros(4,np.int64);predictions={};patients={};net.eval()
    with torch.no_grad():
        for e,features in cached:
            score=np.asarray(net.head(features).tolist(),np.float32);pred=np.full(len(e['valid']),-1,np.int64);pred[e['valid']]=score.argmax(1);rc=np.zeros((4,5),np.int64)
            for i,j in zip(e['ids'],e['mapped']):rc[int(d['y'][i]),4 if j<0 or not e['valid'][j] else int(pred[j])]+=1
            re=np.bincount(pred[e['unmatched']],minlength=4);c+=rc;extra+=re;pc,pe=patients.setdefault(e['subject'],(np.zeros((4,5),np.int64),np.zeros(4,np.int64)));pc+=rc;pe+=re;predictions[e['record']]=(pred,score)
    return metric(c,extra),predictions,{s:metric(*v) for s,v in patients.items()}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--dataset',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--train',action='store_true');ap.add_argument('--epochs',type=int,default=40);ap.add_argument('--fold-seconds',type=int,default=180);ap.add_argument('--batch-seconds',type=int,default=600);ap.add_argument('--seed',type=int,default=2026110202);args=ap.parse_args()
    if not 1<=args.epochs<=40 or not 1<=args.fold_seconds<=600 or not 1<=args.batch_seconds<=1800:ap.error('本入口只提供有限预算；更改上限需先重新明确实验协议')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);p,d,a,events,pair=dataset(args.dataset.resolve());parts=[split(p,d,a,events,pair,f) for f in range(3)];files=[HERE/'network.py',HERE/'features.py',Path(__file__),HERE/'prepare.py',HERE/'protocol.json',HERE/'files.json'];sources={str(v.relative_to(ROOT)).replace('\\','/'):sha(v) for v in files};manifest=read(HERE/'files.json')
    for name,row in manifest['files'].items():
        if sha(HERE/name)!=row['sha256']:raise ValueError('交接资产SHA不符：'+name)
    write(out/'protocol.json',dict(task='从H27出发的无教师参考训练，接手者可改方法；不代表重跑原H27优化轨迹',train=args.train,max_fits=3 if args.train else 0,epochs=args.epochs,fold_seconds=args.fold_seconds,batch_seconds=args.batch_seconds,threads=4,seed=args.seed,sources=sources,input_manifest_sha256=sha(args.dataset/'manifest.json'),loss='reference only: focal gamma2, natural original mass, F*.2, NO teacher KL; differs from historical H27',selection='full automatic N/S/V mean F1 incl missing and extras',splits=[v[-1] for v in parts],test_loaded=False));start=time.monotonic();results=[]
    for f,(z,y,mass,meta) in enumerate(parts):
        torch.manual_seed(args.seed+f);net=load_model(f);folder=out/f'fold_{f}';folder.mkdir();vi=np.flatnonzero(np.isin(d['subject'],p['folds'][f]))
        if not args.train:
            small={k:v[:8] for k,v in z.items()};features=encode(net,small);value=net.head(features);labels=tensor(y[:8]);ce=nn.functional.cross_entropy(value,labels,reduction='none');pt=value.softmax(1).gather(1,labels[:,None]).squeeze(1);loss=(ce*(1-pt).square()).mean();assert torch.isfinite(loss);loss.backward();assert all(v.grad is not None and torch.isfinite(v.grad).all() for v in net.head.parameters());write(folder/'preflight.json',dict(passed=True,fit_count=0,feature_dimensions=int(features.shape[1]),split=meta));continue
        for par in list(net.wave.parameters())+list(net.rr.parameters()):par.requires_grad_(False)
        clock=time.monotonic();features=encode(net,z);cached=[];steps=0
        for e in events:
            if e['subject'] in p['folds'][f]:cached.append((e,encode(net,{k:e[k][e['valid']] for k in FIELDS})))
        weights=mass.copy();weights[y==3]*=.2;weights=tensor(weights/weights.mean());ty=tensor(y);opt=torch.optim.AdamW(net.head.parameters(),lr=.0003,weight_decay=.001);gen=torch.Generator().manual_seed(args.seed+f);best=automatic(net,cached,d)[0]['priority_f1'];best_epoch=0;done=0;torch.save(net.state_dict(),folder/'best_weights.pt')
        for epoch in range(1,args.epochs+1):
            if time.monotonic()-start>args.batch_seconds or time.monotonic()-clock>args.fold_seconds:break
            net.head.train();order=torch.randperm(len(y),generator=gen);finished=True
            for offset in range(0,len(y),512):
                if time.monotonic()-start>args.batch_seconds or time.monotonic()-clock>args.fold_seconds:finished=False;break
                ix=order[offset:offset+512];opt.zero_grad(set_to_none=True);logit=net.head(features[ix]);ce=nn.functional.cross_entropy(logit,ty[ix],reduction='none');pt=logit.softmax(1).gather(1,ty[ix,None]).squeeze(1);loss=(ce*(1-pt).square()*weights[ix]).mean();assert torch.isfinite(loss);loss.backward();nn.utils.clip_grad_norm_(net.head.parameters(),5,error_if_nonfinite=True);opt.step();steps+=1
            if not finished:break
            done=epoch;met=automatic(net,cached,d)[0]
            with (folder/'epochs.jsonl').open('a',encoding='utf-8') as h:h.write(json.dumps(dict(epoch=epoch,automatic=met))+'\n')
            if met['priority_f1']>best:best=met['priority_f1'];best_epoch=epoch;torch.save(net.state_dict(),folder/'best_weights.pt')
            if epoch>=20 and epoch-best_epoch>=12:break
        net.load_state_dict(torch.load(folder/'best_weights.pt',weights_only=True));met,pred,patients=automatic(net,cached,d)
        for record,(label,score) in pred.items():np.savez_compressed(folder/(record+'_auto.npz'),prediction=label,logits=score)
        expert_score=logits(net,d['x'][vi],d['rr'][vi],d['background'][vi],d['history_count'][vi],d['history_rr'][vi]);np.savez_compressed(folder/'expert_predictions.npz',indices=vi,true=d['y'][vi],prediction=expert_score.argmax(1),logits=expert_score)
        ec=np.zeros((4,5),np.int64);np.add.at(ec,(d['y'][vi],expert_score.argmax(1)),1)
        result=dict(fold=f,best_epoch=best_epoch,completed_epochs=done,optimizer_steps=steps,expert=metric(ec,np.zeros(4,np.int64)),automatic=met,patients=patients,weights_sha256=sha(folder/'best_weights.pt'));write(folder/'result.json',result);results.append(result)
    write(out/'completion.json',dict(completed=True,fits=sum(v['optimizer_steps']>0 for v in results),folds=results,test_loaded=False,independent_weight_replay_pending=args.train,hardware=False));print('TRAINING_FINISHED' if args.train else 'PREFLIGHT_PASSED_NO_FIT')
if __name__=='__main__':main()
