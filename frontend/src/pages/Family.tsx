// 账户模块：家庭邀请确认、记录共享与站内通知。
import { useEffect, useState, FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { request, post, Grant, Notification } from '../services/api';

const STATUS: Record<Grant['status'], string> = {
  pending: '等待确认', accepted: '共享中', declined: '已拒绝', revoked: '已撤回', expired: '已过期',
};

const ACTIVITY_TABS = [
  {id: 'received', label: '收到的邀请'},
  {id: 'sent', label: '发出的邀请'},
  {id: 'notifications', label: '站内通知'},
] as const;

export default function Family() {
  const [sent, setSent] = useState<Grant[]>([]);
  const [received, setReceived] = useState<Grant[]>([]);
  const [notes, setNotes] = useState<Notification[]>([]);
  const [username, setUsername] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activity, setActivity] = useState<(typeof ACTIVITY_TABS)[number]['id']>('received');

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
      await post('/family/grants', {username: username.trim()});
      setUsername('');
      setActivity('sent');
    }, '邀请已发送，等待对方确认');
  }

  const shared = received.filter(item => item.status === 'accepted');
  const sharing = sent.filter(item => item.status === 'accepted');
  const sentInvitations = sent.filter(item => item.status !== 'accepted');
  const pending = received.filter(item => item.status === 'pending');
  const history = received.filter(item => !['accepted', 'pending'].includes(item.status));
  const connectedCount = shared.length + sharing.length;
  const activityCounts = {
    received: pending.length,
    sent: sentInvitations.filter(item => item.status === 'pending').length,
    notifications: notes.length,
  };

  function grantRow(item: Grant, incoming: boolean) {
    const accepted = item.status === 'accepted';
    return <div className="family-grant-row" key={item.id}>
      <div className="family-grant-person">
        <strong>{item.username}</strong>
        <span className={`badge ${accepted ? 'badge-ok' : item.status === 'pending' ? 'badge-warn' : 'badge-muted'}`}>{STATUS[item.status]}</span>
        {accepted && <p className="hint">{incoming ? '对方向你共享记录' : '你向对方共享记录'}</p>}
        {item.status === 'pending' && item.expires_at &&
          <p className="hint">有效期至 {new Date(item.expires_at * 1000).toLocaleString()}</p>}
      </div>
      <div className="actions">
        {accepted && <Link className="button" to={`/family/care/${item.id}`}>亲属关怀</Link>}
        {incoming && item.status === 'pending' && <>
          <button disabled={busy} onClick={() => void act(
            () => post(`/family/invitations/${item.id}/respond`, {accept: true}), '已接受邀请，可以查看共享记录')}>接受邀请</button>
          <button className="secondary" disabled={busy} onClick={() => void act(
            () => post(`/family/invitations/${item.id}/respond`, {accept: false}), '已拒绝邀请')}>拒绝</button>
        </>}
        {incoming && accepted && <button className="secondary" disabled={busy}
          onClick={() => void act(() => request(`/family/invitations/${item.id}`, {method: 'DELETE'}), '已退出共享')}>退出共享</button>}
        {!incoming && (item.status === 'pending' || accepted) && <button className="secondary" disabled={busy}
          onClick={() => void act(async () => {
            await request(`/family/grants/${item.id}`, {method: 'DELETE'});
            setActivity('sent');
          }, accepted ? '已撤回共享授权' : '已撤回邀请')}>
          {item.status === 'pending' ? '撤回邀请' : '撤回授权'}</button>}
      </div>
    </div>;
  }

  return <section className="family-shell family-page">
    <header className="family-heading">
      <h1>家庭协同</h1>
      <p>与家属共享心电记录、协作照护和留言。</p>
    </header>
    <p className="family-status" role="status">{message}</p>

    <div className="family-panels">
      <article className="family-panel family-care-panel" aria-labelledby="family-care-heading">
        <div className="family-panel-heading">
          <h2 id="family-care-heading">已连接的家属</h2>
          {connectedCount > 0 && <span className="badge badge-ok">{connectedCount} 项共享关系</span>}
        </div>
        {loading && <p role="status">正在加载家属关系…</p>}
        {!loading && connectedCount === 0 && <div className="family-care-empty">
          <strong>还没有共享关系</strong>
          <p>家属接受邀请后，你们可以在这里进入亲属关怀。</p>
        </div>}
        {shared.map(item => grantRow(item, true))}
        {sharing.map(item => grantRow(item, false))}
        {shared.length > 0 && <Link className="family-shared-link" to="/records?shared=true">查看共享给我的记录 →</Link>}
      </article>

      <article className="family-panel family-invite-panel" aria-labelledby="family-invite-heading">
        <h2 id="family-invite-heading">邀请家属</h2>
        <form className="family-invite-form" onSubmit={invite}>
          <label>家属用户名
            <input required maxLength={80} autoComplete="off" autoCapitalize="none" spellCheck={false}
              placeholder="输入对方已注册的用户名" value={username} onChange={e => setUsername(e.target.value)} />
          </label>
          <button disabled={busy || !username.trim()}>发送邀请</button>
        </form>
        <p className="family-invite-help">对方接受后开始共享，你可以随时撤回授权。</p>
      </article>

      <article className="family-panel family-activity-panel" aria-labelledby="family-activity-heading">
        <div className="family-panel-heading">
          <h2 id="family-activity-heading">家庭动态</h2>
          <div className="family-segmented family-activity-switch" role="group" aria-label="选择动态类型">
            {ACTIVITY_TABS.map(({id, label}) => <button key={id} type="button"
              aria-pressed={activity === id} aria-controls="family-activity-content"
              onClick={() => setActivity(id)}>
              {label}
              {activityCounts[id] > 0 && <span className="family-activity-count">{activityCounts[id]}</span>}
            </button>)}
          </div>
        </div>
        <div className="family-activity-content" id="family-activity-content">
          {loading && <p className="family-activity-empty">正在加载动态…</p>}
          {activity === 'received' && <>
            {!loading && !pending.length && <p className="family-activity-empty">暂无待确认的邀请</p>}
            {pending.map(item => grantRow(item, true))}
            {history.length > 0 && <details><summary>邀请历史</summary>{history.map(item => grantRow(item, true))}</details>}
          </>}
          {activity === 'sent' && <>
            {!loading && !sentInvitations.length && <p className="family-activity-empty">暂无待确认或已结束的邀请</p>}
            {sentInvitations.map(item => grantRow(item, false))}
          </>}
          {activity === 'notifications' && <>
            {!loading && !notes.length && <p className="family-activity-empty">暂无站内通知</p>}
            {notes.length > 0 && <ul className="family-notifications">
              {notes.map(note => <li key={note.id}>{note.message}</li>)}
            </ul>}
          </>}
        </div>
      </article>
    </div>
  </section>;
}
