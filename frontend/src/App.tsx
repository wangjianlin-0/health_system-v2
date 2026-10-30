// 账户模块：公共框架与身份入口。记录页面由记录模块维护。
import { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Analyze from './pages/Analyze';
import Records from './pages/Records';
import Family from './pages/Family';

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(sessionStorage.getItem('ecg_token')));
  useEffect(() => {const logout=()=>setSignedIn(false); window.addEventListener('ecg:logout',logout);return()=>window.removeEventListener('ecg:logout',logout);},[]);
  if (!signedIn) return <Login onLogin={()=>setSignedIn(true)} />;
  return <Layout><Routes>
    <Route path="/" element={<Dashboard />} /><Route path="/analyze" element={<Analyze />} />
    <Route path="/records" element={<Records />} /><Route path="/records/:id" element={<Analyze />} />
    <Route path="/family" element={<Family />} /><Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Layout>;
}
