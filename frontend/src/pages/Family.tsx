// 账户模块：家庭邀请确认、记录共享与站内通知。
import { useEffect, useState, FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { request, post, Grant, Notification } from '../services/api';

const STATUS: Record<Grant['status'], string> = {
  pending: '等待确认', accepted: '共享中', declined: '已拒绝', revoked: '已撤回', expired: '已过期',
};

export default function Family() {
  const [sent, setSent] = useState<Grant[]>([]);
  const [received, setReceived] = useState<Grant[]>([]);
  const [notes, setNotes] = useState<Notification[]>([]);
  const [username, setUsername] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    const [outgoing, incoming, notifications] = await Promise.all([
      request<Grant[]>('/family/grants'), request<Grant[]>('/family/invitations'),
      request<Notification[]>('/family/notifications'),
    ]);
    setSent(outgoing); setReceived(incoming); setNotes(notifications);
  }

  useEffect(() => {
    void refresh().catch(e => setMessage(e.message)).finally(() => setLoading(false));
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh().catch(e => setMessage(e.message));
    }, 10000);
    return () => window.clearInterval(timer);
  }, []);

  async function act(action: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage('');
    try {
      await action(); setMessage(success); await refresh();
    } catch (e) { setMessage((e as Error).message); }
    finally { setBusy(false); }
  }

  function invite(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      await post('/family/grants', {username: username.trim()}); setUsername('');
    }, '邀请已发送，等待对方确认');
  }

  const shared = received.filter(item => item.status === 'accepted');
  const pending = received.filter(item => item.status === 'pending');
  const history = received.filter(item => !['accepted', 'pending'].includes(item.status));

  function grantRow(item: Grant, incoming: boolean) {
    return <div className="family-grant-row" key={item.id}>
      <div><strong>{item.username}</strong><span className="badge badge-muted">{STATUS[item.status]}</span>
        {item.status === 'pending' && item.expires_at &&
          <p className="hint">有效期至 {new Date(item.expires_at * 1000).toLocaleString()}</p>}
      </div>
      <div className="actions">
        {incoming && item.status === 'pending' && <>
          <button disabled={busy} onClick={() => void act(
            () => post(`/family/invitations/${item.id}/respond`, {accept: true}), '已接受邀请，可以查看共享记录')}>接受邀请</button>
          <button className="secondary" disabled={busy} onClick={() => void act(
            () => post(`/family/invitations/${item.id}/respond`, {accept: false}), '已拒绝邀请')}>拒绝</button>
        </>}
        {incoming && item.status === 'accepted' && <button className="secondary" disabled={busy}
          onClick={() => void act(() => request(`/family/invitations/${item.id}`, {method: 'DELETE'}), '已退出共享')}>退出共享</button>}
        {!incoming && ['pending', 'accepted'].includes(item.status) && <button className="secondary" disabled={busy}
          onClick={() => void act(() => request(`/family/grants/${item.id}`, {method: 'DELETE'}), '邀请或授权已撤回')}>
          {item.status === 'pending' ? '撤回邀请' : '撤回授权'}</button>}
      </div>
    </div>;
  }

  return <section className="family-page">
    <p className="eyebrow">用户与家庭协同</p><h1>家庭协同</h1>
    <p>邀请已注册的家属查看你的记录，对方接受后生效。你可以随时撤回共享权限。</p>
    <div className="family-sections"><article className="family-panel family-invite"><h2>邀请家属</h2><form onSubmit={invite}>
      <label>家属用户名<input required maxLength={80} value={username} onChange={e => setUsername(e.target.value)} /></label>
      <button disabled={busy || !username.trim()}>发送邀请</button>
    </form>
    <p role="status">{message}</p></article><article className="family-panel">
    {loading && <p role="status">正在加载家庭信息…</p>}
    <h2>收到的邀请</h2>
    {!loading && !pending.length && <p className="hint">暂无待确认邀请</p>}
    {pending.map(item => grantRow(item, true))}
    </article><article className="family-panel"><h2>共享给我的记录</h2>
    {!loading && !shared.length && <p className="hint">暂无共享关系</p>}
    {shared.map(item => grantRow(item, true))}
    {shared.length > 0 && <Link className="link" to="/records?shared=true">查看共享记录 →</Link>}
    </article><article className="family-panel"><h2>我发出的邀请与授权</h2>
    {!loading && !sent.length && <p className="hint">暂无邀请</p>}
    {sent.map(item => grantRow(item, false))}
    {history.length > 0 && <details><summary>邀请历史</summary>{history.map(item => grantRow(item, true))}</details>}
    </article><article className="family-panel family-notifications"><h2>站内通知</h2>
    {!loading && !notes.length && <p className="hint">暂无通知</p>}
    {notes.map(note => <p key={note.id}>{note.message}</p>)}</article></div>
  </section>;
}
