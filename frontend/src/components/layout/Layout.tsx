import { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { post } from '../../services/api';
export default function Layout({children}: {children:ReactNode}) {
  async function logout() {
    try {await post('/auth/logout');} finally {sessionStorage.removeItem('ecg_token');window.dispatchEvent(new Event('ecg:logout'));}
  }
  return <><header className="app-header"><strong>未卜心知</strong><span>家庭心电辅助记录</span><div className="header-links"><NavLink to="/guide"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 6c-2.7-1.7-5.7-1.9-9-1v13c3.3-.9 6.3-.7 9 1 2.7-1.7 5.7-1.9 9-1V5c-3.3-.9-6.3-.7-9 1Z"/><path d="M12 6v13"/></svg>使用手册</NavLink><NavLink to="/profile"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-4 3-6 7-6s7 2 7 6"/></svg>个人中心</NavLink></div><button className="secondary" onClick={()=>{void logout().catch(()=>{});}}>退出</button></header>
    <main>
    <nav><NavLink to="/">概览</NavLink><NavLink to="/monitor">实时监测</NavLink><NavLink to="/analyze">导入与分析</NavLink><NavLink to="/records">历史记录</NavLink><NavLink to="/family">家庭协同</NavLink></nav>{children}</main></>;
}
