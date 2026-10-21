import { useEffect, useState, FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { post, request, RecordResult } from '../services/api';
import Waveform from '../components/Waveform';
export default function Analyze(){
  const {id}=useParams();const navigate=useNavigate();
  const [file,setFile]=useState<File|null>(null),[rate,setRate]=useState(250),[record,setRecord]=useState<RecordResult|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{let active=true;setRecord(null);setError('');if(id)request<RecordResult>('/records/'+id).then(r=>{if(active)setRecord(r);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[id]);
  async function run(replay=false){setBusy(true);setError('');try{let r:RecordResult;if(replay)r=await post('/acquisition/replay');else{if(!file)throw Error('请选择 CSV');const body=new FormData();body.append('file',file);body.append('sample_rate_hz',String(rate));r=await request('/analyze/ecg',{method:'POST',body});}navigate('/records/'+r.id);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section><p className="eyebrow">{id?'健康记录':'创建健康记录'}</p><h1>{id?'记录详情':'添加心电数据'}</h1>{!id&&<><p>上传单列 CSV 文件（单位 mV，支持 value、sample 或 mv 表头），并填写对应采样率。没有文件时，可直接使用示例数据体验完整流程。</p><form onSubmit={(e:FormEvent)=>{e.preventDefault();void run();}}><label>心电数据文件（CSV）<input type="file" accept=".csv" required onChange={e=>setFile(e.target.files?.[0]||null)} /></label><label>采样率（Hz）<input type="number" min="50" max="2000" value={rate} onChange={e=>setRate(Number(e.target.value))} required /></label><div className="actions"><button disabled={busy}>上传并查看结果</button><button type="button" className="secondary" disabled={busy} onClick={()=>void run(true)}>使用示例数据体验</button></div></form></>}
    <p role="status">{busy?'正在分析并保存记录…':error}</p>{record&&<article><p>{new Date(record.created_at).toLocaleString()} · {record.result.source}</p><h2>{record.result.quality.status==='insufficient'?'数据不足，暂时无法分析':'数据已完成基础质量检查'}</h2><p>{record.result.quality.scope}</p><p>{record.result.quality.reasons.join('；')}</p><Waveform values={record.result.waveform} duration={record.result.duration_sec} unit={record.result.unit} /><p>{record.result.prediction.explanation}</p><p>分析分类：{record.result.prediction.label??'暂无结果'} · 心率：暂未提供</p></article>}</section>;
}
