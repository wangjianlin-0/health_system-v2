import { useState, FormEvent } from 'react';
import { post, saveSession, SessionResponse } from '../services/api';
export default function Login({onLogin,message:initialMessage=''}:{onLogin:()=>void;message?:string}) {
  const [username,setUsername]=useState(''), [password,setPassword]=useState(''), [message,setMessage]=useState(initialMessage), [busy,setBusy]=useState(false);
  async function submit(register=false) {
    setBusy(true);setMessage('');
    try {
      if(register){await post('/auth/register',{username,password});setMessage('注册成功，请登录');}
      else {const data=await post<SessionResponse>('/auth/login',{username,password});saveSession(data);onLogin();}
    } catch(e){setMessage((e as Error).message);}finally{setBusy(false);}
  }
  return <main className="login"><section><p className="eyebrow">家庭心电健康助手</p><h1>欢迎使用未卜心知</h1><p>登录后即可管理心电记录、查看分析结果，并与家人安全共享。首次使用可直接创建账号。</p>
    <form onSubmit={(e:FormEvent)=>{e.preventDefault();void submit();}}><label>用户名<input required value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" /></label>
    <label>密码（至少 8 位）<input required type="password" minLength={8} value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" /></label>
    <div className="actions"><button disabled={busy}>登录</button><button disabled={busy || !username || password.length<8} type="button" className="secondary" onClick={()=>void submit(true)}>创建账号</button></div></form><p role="status">{message}</p></section></main>;
}
