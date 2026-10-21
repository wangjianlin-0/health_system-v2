import { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { clearSession, currentUsername, post } from '../../services/api';
export default function Layout({children}: {children:ReactNode}) {
  async function logout() {
    try {await post('/auth/logout');} finally {clearSession();}
  }
  return <><header><strong>未卜心知</strong><span>家庭心电健康助手</span><span className="account">{currentUsername()}</span><button className="secondary" onClick={()=>{void logout().catch(()=>{});}}>退出登录</button></header>
    <main><aside><strong>使用提示</strong>：上传心电数据即可生成健康记录；如果暂时没有文件，也可以使用示例数据快速体验。分析结果仅供健康管理参考，不能替代专业医疗诊断。</aside>
    <nav><NavLink to="/">首页</NavLink><NavLink to="/analyze">新增记录</NavLink><NavLink to="/records">我的记录</NavLink><NavLink to="/family">家庭共享</NavLink></nav>{children}</main></>;
}
