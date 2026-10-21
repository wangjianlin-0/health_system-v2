import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { request, RecordRow } from '../services/api';
export default function Records(){
  const [rows,setRows]=useState<RecordRow[]>([]),[shared,setShared]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(true);
  useEffect(()=>{let active=true;setBusy(true);setError('');request<RecordRow[]>('/records?shared='+shared).then(r=>{if(active)setRows(r);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setBusy(false);});return()=>{active=false;};},[shared]);
  return <section><p className="eyebrow">我的健康档案</p><h1>心电记录</h1><p>你创建和保存的分析结果会按时间显示在这里。</p><label className="inline"><input type="checkbox" checked={shared} onChange={e=>setShared(e.target.checked)} />只看家人分享给我的记录</label><p role="status">{busy?'正在加载记录…':error}</p>{!busy&&!error&&!rows.length&&<p>{shared?'还没有家人分享记录给你':'还没有记录，去创建第一份心电记录吧'}</p>}{!busy&&!error&&rows.map(r=><div className="row" key={r.id}><span>{new Date(r.created_at).toLocaleString()}<small>记录编号：{r.id}</small></span><Link to={'/records/'+r.id}>查看详情</Link></div>)}</section>;
}
