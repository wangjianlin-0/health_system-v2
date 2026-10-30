import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AnalysisTask, RecordPage, RecordTrends, TaskPage, localTimezone, request,
} from '../services/api';
import { TaskStatusBadge } from '../components/badges';

export default function Dashboard() {
  const [device, setDevice] = useState('读取采集状态…');
  const [summary, setSummary] = useState<RecordTrends | null>(null);
  const [recent, setRecent] = useState<RecordPage['items']>([]);
  const [active, setActive] = useState<AnalysisTask[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    Promise.all([
      request<{message: string}>('/acquisition/status'),
      request<RecordTrends>(`/records/trends?days=30&timezone=${encodeURIComponent(localTimezone())}`),
      request<RecordPage>('/records?page=1&page_size=5'),
      request<TaskPage>('/tasks?status=pending,running&page=1&page_size=5'),
    ]).then(([status, trend, records, tasks]) => {
      if (!mounted) return;
      setDevice(status.message);
      setSummary(trend);
      setRecent(records.items);
      setActive(tasks.items);
    }).catch(caught => {
      if (mounted) {
        setError((caught as Error).message);
        setDevice('暂时无法读取采集状态');
      }
    });
    return () => {mounted = false;};
  }, []);

  const stats = summary?.summary;

  return <section>
    <p className="eyebrow">五人协作框架</p>
    <h1>从一份记录开始</h1>
    <p>{device}</p>
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <div className="actions">
      <Link className="button" to="/analyze">导入或回放</Link>
      <Link className="button secondary" to="/records">查看历史</Link>
    </div>

    {active.length > 0 && <div className="active-tasks">
      <h2>进行中的任务</h2>
      {active.map(task => <Link className="active-task" key={task.id} to={`/analyze?task=${task.id}`}>
        <TaskStatusBadge status={task.status} />
        <span className="mono">{task.id}</span>
        <span>{task.stage ?? 'queued'}</span>
      </Link>)}
    </div>}

    <div className="stat-grid">
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

    <div className="grid">
      <article><h2>记录与分析</h2><p>上传、结果、历史与数据服务</p></article>
      <article><h2>用户与家庭</h2><p>应用框架、账号、授权与站内提示</p></article>
      <article><h2>采集与分析模块</h2><p>设备接入<br />数据与信号<br />AI 与分析集成</p></article>
    </div>
  </section>;
}
