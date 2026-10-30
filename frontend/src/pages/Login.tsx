// 账户模块：身份页面及其接口。
import { useState, FormEvent } from 'react';
import { post } from '../services/api';
export default function Login({onLogin}:{onLogin:()=>void}) {
  const [username,setUsername]=useState(''), [password,setPassword]=useState(''), [message,setMessage]=useState(''), [busy,setBusy]=useState(false);
  async function submit(register=false) {
    setBusy(true);setMessage('');
    try {
      if(register){await post('/auth/register',{username,password});setMessage('注册成功，请登录');}
      else {const data=await post<{token:string}>('/auth/login',{username,password});sessionStorage.setItem('ecg_token',data.token);onLogin();}
    } catch(e){setMessage((e as Error).message);}finally{setBusy(false);}
  }
  return <main className="login"><section><p className="eyebrow">用户与家庭协同</p><h1>开始健康记录</h1><p>创建本地账号，查看自己的记录与家庭授权。</p>
    <form onSubmit={(e:FormEvent)=>{e.preventDefault();void submit();}}><label>用户名<input required value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" /></label>
    <label>密码（至少 8 位）<input required type="password" minLength={8} value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" /></label>
    <div className="actions"><button disabled={busy}>登录</button><button disabled={busy || !username || password.length<8} type="button" className="secondary" onClick={()=>void submit(true)}>注册</button></div></form><p role="status">{message}</p></section></main>;
}
