import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AnalysisTask, Notification, RecordPage, RecordTrends, TaskPage, localTimezone, recordSourceLabel, request,
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
  return <section className="dashboard-page portal-dashboard">
    <div className="portal-top">
      <div className="portal-welcome">
        <p className="eyebrow">个人健康档案</p>
        <h1>欢迎回来</h1>
        <p>从一次测量开始，集中查看心电记录与家庭共享。</p>
        <div className="portal-primary-actions">
          <Link className="button" to="/monitor">开始测量</Link>
          <Link className="button secondary" to="/analyze">导入心电文件</Link>
        </div>
        <p className="portal-device">采集状态：{device}</p>
      </div>
      <div className="portal-summary">
        <h2>近 30 天概览</h2>
        <div className="portal-stat-grid">
          <div><strong>{stats?.total ?? 0}</strong><span>次测量</span></div>
          <div><strong>{stats?.heart_rate_days ?? 0}</strong><span>天有心率数据</span></div>
          <div><strong>{stats?.avg_heart_rate_bpm ?? '—'}</strong><span>平均心率 · 次/分</span></div>
          <div><strong>{stats?.insufficient ?? 0}</strong><span>次质量不足</span></div>
        </div>
        <Link to="/records">查看完整历史与趋势 →</Link>
      </div>
    </div>
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <div className="portal-columns">
      <article className="portal-panel portal-recent">
        <div className="portal-panel-head"><div><p className="eyebrow">测量时间线</p><h2>最近记录</h2></div>
          <Link to="/records">查看全部 →</Link></div>
        {recent.length === 0 && <div className="portal-empty">还没有测量记录。可以导入 CSV 或尝试合成回放。</div>}
        {recent.map(record => <Link className="portal-record" key={record.id} to={'/records/' + record.id}>
          <div><strong>{record.title}</strong><span>{new Date(record.created_at).toLocaleString()} · {recordSourceLabel(record.source)}</span></div>
          <span>{record.heart_rate_bpm == null ? '暂无心率' : record.heart_rate_bpm + ' 次/分'}</span>
        </Link>)}
      </article>
      <div className="portal-side">
        <article className="portal-panel">
          <p className="eyebrow">家庭共享</p><h2>与家人一起回顾</h2>
          <p>邀请已注册的家属。对方确认后可查看共享记录，你可以随时撤回。</p>
          {notifications.length > 0 && <p className="portal-notice">{notifications[0].message}</p>}
          <Link to="/family">管理邀请与授权 →</Link>
        </article>
        <article className="portal-panel">
          <p className="eyebrow">进行中的分析</p><h2>{active.length} 个任务</h2>
          {active.length === 0 ? <p>当前没有正在处理的任务。</p> :
            active.map(task => <Link key={task.id} className="portal-task" to={'/analyze?task=' + task.id}>
              <TaskStatusBadge status={task.status} />查看任务进度 →</Link>)}
          <Link to="/guide">第一次使用？查看操作手册 →</Link>
        </article>
      </div>
    </div>
    <p className="portal-safety">记录与分析结果用于辅助回顾，不能单独用于医疗诊断。</p>
  </section>;
}
