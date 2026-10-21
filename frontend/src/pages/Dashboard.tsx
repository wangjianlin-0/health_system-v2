import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { request } from '../services/api';
export default function Dashboard(){
  const [status,setStatus]=useState('正在检查服务状态…');
  useEffect(()=>{let active=true;request<{connected:boolean}>('/acquisition/status').then(r=>{if(active)setStatus(r.connected?'设备已连接，可以开始记录':'现在可以使用示例数据体验完整流程');}).catch(()=>{if(active)setStatus('服务暂时不可用，请稍后重试');});return()=>{active=false;};},[]);
  return <section><p className="eyebrow">健康记录中心</p><h1>从第一份心电记录开始</h1><p>{status}</p><div className="actions"><Link className="button" to="/analyze">开始创建记录</Link><Link className="button secondary" to="/records">查看我的记录</Link></div>
    <div className="grid"><article><p className="eyebrow">步骤 01</p><h2>添加心电数据</h2><p>上传已有的 CSV 文件，或使用示例数据快速体验，无需额外配置。</p></article><article><p className="eyebrow">步骤 02</p><h2>查看分析结果</h2><p>集中查看心电波形、数据质量和分析说明，历史结果自动保存。</p></article><article><p className="eyebrow">步骤 03</p><h2>安全分享给家人</h2><p>按需开放记录列表或详情权限，授权范围可以随时调整或撤回。</p></article></div></section>;
}
