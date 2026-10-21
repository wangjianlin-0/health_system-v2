import { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Analyze from './pages/Analyze';
import Records from './pages/Records';
import Family from './pages/Family';
import { clearSession, hasActiveSession, sessionExpiresAt } from './services/api';

export default function App() {
  const hadToken = Boolean(sessionStorage.getItem('ecg_token'));
  const [signedIn, setSignedIn] = useState(hasActiveSession());
  const [loginMessage, setLoginMessage] = useState(hadToken && !hasActiveSession() ? '登录已过期，请重新登录' : '');
  useEffect(() => {
    const logout = (event: Event) => {
      setSignedIn(false);
      setLoginMessage((event as CustomEvent<{reason?: string}>).detail?.reason || '');
    };
    window.addEventListener('ecg:logout', logout);
    return () => window.removeEventListener('ecg:logout', logout);
  }, []);
  useEffect(() => {
    if (!signedIn) return;
    const expiresAt = sessionExpiresAt();
    if (!expiresAt) return;
    const remaining = expiresAt * 1000 - Date.now();
    if (remaining <= 0) {clearSession('登录已过期，请重新登录');return;}
    const timer = window.setTimeout(() => clearSession('登录已过期，请重新登录'), remaining);
    return () => window.clearTimeout(timer);
  }, [signedIn]);
  if (!signedIn) return <Login message={loginMessage} onLogin={()=>{setLoginMessage('');setSignedIn(true);}} />;
  return <Layout><Routes>
    <Route path="/" element={<Dashboard />} /><Route path="/analyze" element={<Analyze />} />
    <Route path="/records" element={<Records />} /><Route path="/records/:id" element={<Analyze />} />
    <Route path="/family" element={<Family />} /><Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Layout>;
}
