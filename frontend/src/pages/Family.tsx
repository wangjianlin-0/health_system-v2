// 账户模块：家庭业务页面与接口。
import { useEffect, useState, FormEvent } from 'react';
import { request, post, Grant, Notification } from '../services/api';
export default function Family(){
  const [rows,setRows]=useState<Grant[]>([]),[notes,setNotes]=useState<Notification[]>([]),[username,setUsername]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  async function refresh(){const [g,n]=await Promise.all([request<Grant[]>('/family/grants'),request<Notification[]>('/family/notifications')]);setRows(g);setNotes(n);}
  useEffect(()=>{void refresh().catch(e=>setMessage(e.message));},[]);
  async function change(id?:string){setBusy(true);try{if(id)await request('/family/grants/'+id,{method:'DELETE'});else await post('/family/grants',{username});await refresh();setMessage(id?'授权已撤回':'已开放记录查看权限');}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}}
  return <section><p className="eyebrow">用户与家庭协同</p><h1>家庭协同</h1><p>向已注册账号开放记录查看权限。当前为直接授权原型，邀请确认与外部警报尚未实现。</p><form onSubmit={(e:FormEvent)=>{e.preventDefault();void change();}}><label>家属用户名<input required value={username} onChange={e=>setUsername(e.target.value)} /></label><button disabled={busy}>授权查看</button></form><p role="status">{message}</p><h2>我发出的授权</h2>{!rows.length&&<p>暂无授权</p>}{rows.map(g=><div className="row" key={g.id}><span>{g.username} · {g.active?'有效':'已撤回'}</span>{Boolean(g.active)&&<button className="secondary" disabled={busy} onClick={()=>void change(g.id)}>撤回</button>}</div>)}<h2>站内通知</h2>{!notes.length&&<p>暂无通知</p>}{notes.map(n=><p key={n.id}>{n.message} · 站内可查看，非外部投递</p>)}</section>;
}
