import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AnalysisTask, Notification, RecordPage, RecordTrends, TaskPage, localTimezone, request,
} from '../services/api';
import { TaskStatusBadge } from '../components/badges';

export default function Dashboard() {
  const [device, setDevice] = useState('读取采集状态…');
  const [summary, setSummary] = useState<RecordTrends | null>(null);
  const [recent, setRecent] = useState<RecordPage['items']>([]);
  const [active, setActive] = useState<AnalysisTask[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    Promise.all([
      request<{message: string}>('/acquisition/status'),
      request<RecordTrends>(`/records/trends?days=30&timezone=${encodeURIComponent(localTimezone())}`),
      request<RecordPage>('/records?page=1&page_size=5'),
      request<TaskPage>('/tasks?status=pending,running&page=1&page_size=5'),
      request<Notification[]>('/family/notifications'),
    ]).then(([status, trend, records, tasks, notes]) => {
      if (!mounted) return;
      setDevice(status.message);
      setSummary(trend);
      setRecent(records.items);
      setActive(tasks.items);
      setNotifications(notes);
    }).catch(caught => {
      if (mounted) {
        setError((caught as Error).message);
        setDevice('暂时无法读取采集状态');
      }
    });
    return () => {mounted = false;};
  }, []);

  const stats = summary?.summary;

  return <section className="dashboard-page">
    {notifications.length > 0 && <Link className="dashboard-notice" to="/family">
      <span className="dashboard-notice-label">家庭协同</span><span>{notifications[0].message}</span>
      <span className="dashboard-notice-date">站内通知</span><strong>查看通知 →</strong>
    </Link>}
    <div className="dashboard-hero">
      <div className="dashboard-hero-copy">
        <p className="eyebrow">个人与家庭心电记录</p>
        <h1>把每一次测量，整理成可回顾的健康记录</h1>
        <p>本地采集或导入心电数据，查看波形、分析结果与长期趋势。</p>
      </div>
      <div className="dashboard-hero-actions">
        <Link className="button dashboard-primary" to="/monitor">开始测量 <span>→</span></Link>
        <Link className="button secondary" to="/family">家庭协同</Link>
        <Link className="button secondary" to="/records">历史趋势</Link>
      </div>
      <div className="dashboard-device"><span className="dashboard-live-dot" />{device}</div>
    </div>
    {error && <p className="notice notice-error" role="alert">{error}</p>}

    <div className="dashboard-flow"><span>记录流程</span><strong>开始测量</strong><i>→</i><strong>查看波形</strong><i>→</i><strong>阅读分析</strong><i>→</i><strong>保存并回顾</strong></div>

    {active.length > 0 && <div className="active-tasks">
      <h2>进行中的任务</h2>
      {active.map(task => <Link className="active-task" key={task.id} to={`/analyze?task=${task.id}`}>
        <TaskStatusBadge status={task.status} />
        <span className="mono">{task.id}</span>
        <span>{task.stage ?? 'queued'}</span>
      </Link>)}
    </div>}

    <div className="dashboard-feature-grid">
      <article className="dashboard-feature feature-teal"><div><span>01</span><b>开始测量</b><small>实时采集或连接设备</small></div><Link to="/monitor">进入测量 →</Link></article>
      <article className="dashboard-feature feature-blue"><div><span>02</span><b>导入与分析</b><small>上传心电文件或回放示例</small></div><Link to="/analyze">进入分析 →</Link></article>
      <article className="dashboard-feature feature-green"><div><span>03</span><b>查看分析结果</b><small>波形、心率与质量信息</small></div><Link to="/analyze">查看结果 →</Link></article>
      <article className="dashboard-feature feature-violet"><div><span>04</span><b>历史趋势</b><small>按日期查看记录与变化</small></div><Link to="/records">浏览档案 →</Link></article>
    </div>

    <div className="dashboard-summary-grid">
      <div><strong>{stats?.total ?? 0}</strong><span>近 30 天记录</span></div>
      <div><strong>{stats?.insufficient ?? 0}</strong><span>质量不足</span></div>
      <div><strong>{stats?.heart_rate_days ?? 0}</strong><span>有心率的日期</span></div>
      <div><strong>{stats?.avg_heart_rate_bpm ?? '—'}</strong><span>平均心率（次/分）</span></div>
    </div>

    <article className="recent-records">
      <h2>最近记录</h2>
      {recent.length === 0 && <p className="hint">还没有记录，导入或回放一条开始。</p>}
      {recent.map(record => <Link className="recent-row" key={record.id} to={'/records/' + record.id}>
        <span>{new Date(record.created_at).toLocaleString()}</span>
        <span className="badge badge-muted">{record.source ?? '未知来源'}</span>
        <span>{record.heart_rate_bpm == null ? '—' : `${record.heart_rate_bpm} 次/分`}</span>
      </Link>)}
      {recent.length > 0 && <Link className="link" to="/records">查看全部 →</Link>}
    </article>

  </section>;
}
