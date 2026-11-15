import { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { post } from '../../services/api';
export default function Layout({children}: {children:ReactNode}) {
  async function logout() {
    try {await post('/auth/logout');} finally {sessionStorage.removeItem('ecg_token');window.dispatchEvent(new Event('ecg:logout'));}
  }
  return <><header className="app-header"><strong>未卜心知</strong><span>家庭心电辅助记录</span><button className="secondary" onClick={()=>{void logout().catch(()=>{});}}>退出</button></header>
    <main>
    <nav><NavLink to="/">概览</NavLink><NavLink to="/monitor">实时监测</NavLink><NavLink to="/analyze">导入与分析</NavLink><NavLink to="/records">历史记录</NavLink><NavLink to="/family">家庭协同</NavLink></nav>{children}</main></>;
}
