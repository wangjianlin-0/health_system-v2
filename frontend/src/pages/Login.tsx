// 账户模块：公共登录与注册入口。
import { FormEvent, useState } from 'react';
import { post } from '../services/api';

type Mode = 'login' | 'register';

export default function Login({onLogin}: {onLogin: () => void}) {
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    try {
      if (mode === 'register') {
        await post('/auth/register', {username, password});
        setMode('login');
        setMessage('账号已创建，请登录。');
      } else {
        const data = await post<{token: string}>('/auth/login', {username, password});
        sessionStorage.setItem('ecg_token', data.token);
        onLogin();
      }
    } catch (caught) {
      setMessage((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-screen">
    <section className="auth-intro">
      <div className="auth-brand"><span className="auth-brand-mark">心</span><span>家庭心电记录</span></div>
      <div className="auth-intro-copy">
        <p className="auth-kicker">记录 · 查看 · 回顾</p>
        <h1>让每一次心电测量<br />都有迹可循</h1>
        <p className="auth-lead">集中保存心电记录，查看波形、分析结果和长期变化，方便家人一起回顾。</p>
      </div>
      <div className="auth-wave-card">
        <div className="auth-wave-meta"><span>心电波形示意</span><span>记录与趋势</span></div>
        <svg viewBox="0 0 720 150" role="img" aria-label="心电波形示意图">
          <defs>
            <pattern id="auth-small-grid" width="18" height="18" patternUnits="userSpaceOnUse"><path d="M18 0H0V18" fill="none" stroke="#253047" strokeWidth="1" /></pattern>
            <pattern id="auth-large-grid" width="90" height="90" patternUnits="userSpaceOnUse"><rect width="90" height="90" fill="url(#auth-small-grid)" /><path d="M90 0H0V90" fill="none" stroke="#39445b" strokeWidth="1" /></pattern>
          </defs>
          <rect width="720" height="150" rx="10" fill="url(#auth-large-grid)" />
          <path d="M0 83H35l10-2 8-12 10 14h24l8 4 10-5 8-58 9 81 9-28 12 6h30l10-4 12-17 12 18h30l10 3 8-4 10-11 10 13h24l8 3 10-4 8-58 10 81 9-28 11 6h30l11-4 12-17 11 18h30l10 3 9-4 10-11 10 13h24l8 3 10-4 8-58 10 81 9-28 12 6h30l10-4 12-17 12 18h30l10 3 8-4 10-11 10 13h35" fill="none" stroke="#61c3b0" strokeWidth="2.5" strokeLinejoin="round" />
        </svg>
        <div className="auth-wave-footer"><span>实时采集与 CSV 导入</span><span>波形 · 心率 · 历史</span></div>
      </div>
      <div className="auth-benefits">
        <div><span>01</span><strong>记录测量</strong><p>导入心电 CSV 或连接采集设备</p></div>
        <div><span>02</span><strong>查看分析</strong><p>回顾波形、心率和信号质量</p></div>
        <div><span>03</span><strong>家庭协同</strong><p>按授权查看共享记录与站内通知</p></div>
      </div>
    </section>

    <section className="auth-panel">
      <div className="auth-panel-heading">
        <p className="eyebrow">欢迎使用</p>
        <h2>{mode === 'login' ? '登录家庭心电档案' : '创建本地账号'}</h2>
        <p>{mode === 'login' ? '登录后继续查看个人记录与家庭共享内容。' : '创建账号后即可开始保存和管理心电记录。'}</p>
      </div>
      <div className="auth-mode-switch" role="tablist" aria-label="账号操作">
        <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'selected' : ''}
                onClick={() => {setMode('login'); setMessage('');}}>登录</button>
        <button type="button" role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'selected' : ''}
                onClick={() => {setMode('register'); setMessage('');}}>注册</button>
      </div>
      <form className="auth-form" onSubmit={submit}>
        <label>用户名<input required value={username} onChange={event => setUsername(event.target.value)}
          autoComplete="username" placeholder="请输入用户名" /></label>
        <label>密码<input required type="password" minLength={8} value={password}
          onChange={event => setPassword(event.target.value)}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          placeholder={mode === 'register' ? '至少 8 位' : '请输入密码'} /></label>
        {message && <p className="auth-message" role="status">{message}</p>}
        <button className="auth-submit" disabled={busy || !username || password.length < 8}>
          {busy ? '请稍候…' : mode === 'login' ? '登录并继续　→' : '创建账号　→'}
        </button>
      </form>
      <div className="auth-privacy"><span aria-hidden="true">✓</span><p>心电记录保存在本机运行的数据目录中。分析内容仅供辅助参考，不替代专业临床诊断。</p></div>
    </section>
  </main>;
}
