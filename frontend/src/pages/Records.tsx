// 记录模块：历史、趋势、导出与记录删除页面。
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  RecordPage, RecordTrends, downloadFile, localTimezone, request,
} from '../services/api';
import HistoryAdvice from '../components/HistoryAdvice';
import TrendChart from '../components/TrendChart';
import { QualityBadge } from '../components/badges';

const PAGE_SIZES = [10, 20, 50];
const RANGES = [
  {value: '7', label: '7 天'},
  {value: '30', label: '30 天'},
  {value: '90', label: '90 天'},
  {value: 'all', label: '全部'},
];

function fromDate(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - (days - 1));
  return date.toISOString().slice(0, 10);
}

export default function Records() {
  const [search, setSearch] = useSearchParams();
  const page = Math.max(1, Number(search.get('page') ?? '1') || 1);
  const shared = search.get('shared') === 'true';
  const range = search.get('range') ?? '30';
  const quality = search.get('quality') ?? '';
  const rawSize = Number(search.get('size') ?? '10');
  const size = PAGE_SIZES.includes(rawSize) ? rawSize : 10;
  const days = range === 'all' ? 365 : Number(range);

  const [data, setData] = useState<RecordPage | null>(null);
  const [trends, setTrends] = useState<RecordTrends | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState('');
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const params = new URLSearchParams({
      page: String(page), page_size: String(size), shared: String(shared),
    });
    const status = search.get('status');
    if (quality) params.set('quality', quality);
    else if (status === 'normal') params.set('quality', 'basic_checks_passed');
    else if (status === 'insufficient') params.set('quality', 'insufficient');
    if (range !== 'all' && !search.get('from')) params.set('from', fromDate(days));
    if (search.get('from')) params.set('from', search.get('from')!);
    if (search.get('to')) params.set('to', search.get('to')!);
    const trendQuery = new URLSearchParams({
      days: String(days), shared: String(shared), timezone: localTimezone(),
    });
    Promise.all([
      request<RecordPage>('/records?' + params.toString()),
      request<RecordTrends>('/records/trends?' + trendQuery.toString()),
    ]).then(([list, trend]) => {
      if (!active) return;
      setData(list);
      setTrends(trend);
    }).catch(caught => {
      if (active) setError((caught as Error).message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {active = false;};
  }, [page, shared, range, quality, days, size, refresh, search]);

  function update(patch: Record<string, string | null>) {
    const next = new URLSearchParams(search);
    for (const [key, value] of Object.entries(patch)) {
      if (value == null || value === '') next.delete(key);
      else next.set(key, value);
    }
    setSearch(next);
  }

  async function remove(id: string) {
    if (!window.confirm('确定删除这条记录吗？删除后不能恢复。')) return;
    setDeleting(id);
    setError('');
    try {
      await request(`/records/${id}`, {method: 'DELETE'});
      if (data?.items.length === 1 && page > 1) update({page: String(page - 1)});
      setRefresh(value => value + 1);
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setDeleting('');
    }
  }

  const summary = trends?.summary;

  const filteredDays = trends?.days ?? [];
  const rates = filteredDays.map(point => point.heart_rate_bpm).filter((value): value is number => value != null);
  const minRate = rates.length ? Math.min(...rates) : null;
  const maxRate = rates.length ? Math.max(...rates) : null;
  const attentionCount = filteredDays.reduce((sum, point) => sum + (point.quality.insufficient ?? 0), 0);
  const dayFilter = search.get('from') ?? '';
  const statusFilter = search.get('status') ?? 'all';
  const visibleItems = data?.items ?? [];

  return <section className="records-page">
    <div className="records-heading">
      <div><p className="eyebrow">个人健康档案</p><h1>心电历史趋势与档案</h1></div>
      {summary && <span className="records-total">共 {summary.total} 次记录</span>}
      <button className="secondary records-export" onClick={() => void downloadFile('/records/export?format=csv',
        'ecg-history.csv').catch(caught => setError((caught as Error).message))}>导出 CSV</button>
      {!shared && <button className="records-clear" onClick={() => update({from: null, to: null, status: 'all', range: '30', page: '1'})}>清除筛选</button>}
    </div>

    <div className="records-overview">
      <div className="records-trend-panel">
        <div className="records-trend-heading">
          <div><h2>静息心率趋势折线图</h2><span>正常区间 60–100 BPM · 虚线为长期趋势基线</span></div>
          <div className="range-pills" aria-label="趋势时间范围">
            <button className={range === '7' ? 'selected' : ''} onClick={() => update({range: '7', page: '1'})}>过去一周（7天）</button>
            <button className={range === '30' ? 'selected' : ''} onClick={() => update({range: '30', page: '1'})}>过去一月（30天）</button>
          </div>
        </div>
        <div className="trend-kpis">
          <span>平均心率 <strong>{summary?.avg_heart_rate_bpm ?? '—'}</strong> BPM</span>
          <span>波动范围 <strong>{minRate ?? '—'}–{maxRate ?? '—'}</strong> BPM</span>
          <span>有效记录 <strong>{summary?.heart_rate_days ?? 0}</strong> 天</span>
          <span className="trend-kpi-total">共 {summary?.total ?? 0} 条测量</span>
        </div>
        {trends && <TrendChart days={trends.days} />}
        <p className="trend-caption"><strong>趋势观察</strong> 所示为每日平均心率，测量间隔和身体活动可能影响读数。</p>
      </div>
      <div className="records-status-grid">
        <article className="status-card status-ok"><span>正常记录</span><strong>{Math.max(0, (summary?.total ?? 0) - (summary?.insufficient ?? 0))}<small>次</small></strong><p>基础信号检查通过</p></article>
        <article className="status-card status-watch"><span>质量待留意</span><strong>{attentionCount}<small>次</small></strong><p>可在静息状态下复测</p></article>
        <article className="status-card status-advice"><span>有心率数据</span><strong>{summary?.heart_rate_days ?? 0}<small>天</small></strong><p>用于观察个人变化</p></article>
        <article className="status-card status-info"><span>筛选范围</span><strong>{days}<small>天</small></strong><p>可调整下方时间范围</p></article>
      </div>
    </div>

    <div className="filter-bar records-filters">
      <label className="inline">时间范围
        <select value={range} onChange={event => update({range: event.target.value, page: '1'})}>
          {RANGES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </label>
      <label className="inline">质量
        <select value={quality} onChange={event => update({quality: event.target.value, page: '1'})}>
          <option value="">全部</option>
          <option value="basic_checks_passed">基础检查通过</option>
          <option value="insufficient">信号质量不足</option>
        </select>
      </label>
      <label className="inline">
        <input type="checkbox" checked={shared}
               onChange={event => update({shared: event.target.checked ? 'true' : null, page: '1'})} />
        查看授权给我的记录
      </label>
      <label className="inline">每页
        <select value={String(size)} onChange={event => update({size: event.target.value, page: '1'})}>
          {PAGE_SIZES.map(value => <option key={value} value={value}>{value} 条</option>)}
        </select>
      </label>
      {(quality || range !== '30' || shared) &&
        <button className="secondary" onClick={() => update({quality: null, range: '30', shared: null, page: '1'})}>重置筛选</button>}
    </div>

    {!shared && <details className="advice-drawer"><summary>个人观察与建议</summary><HistoryAdvice refresh={refresh} /></details>}

    <p role="status">{loading ? '加载中…' : error}</p>

    {!loading && !error && data && <>
      <div className="archive-heading"><h2>历史记录明细</h2><div className="archive-tabs" aria-label="记录状态筛选">
        <button className={statusFilter === 'all' ? 'selected' : ''} onClick={() => update({status: 'all', page: '1'})}>全部（{data.total}）</button>
        <button className={statusFilter === 'normal' ? 'selected' : ''} onClick={() => update({status: 'normal', page: '1'})}>正常（{Math.max(0, data.total - (summary?.insufficient ?? 0))}）</button>
        <button className={statusFilter === 'insufficient' ? 'selected' : ''} onClick={() => update({status: 'insufficient', page: '1'})}>关注（{summary?.insufficient ?? 0}）</button>
        {dayFilter && <button className="archive-reset" onClick={() => update({from: null, to: null})}>取消日期筛选 ×</button>}
      </div></div>
      {visibleItems.length === 0 && <div className="empty-state">
        <p>{shared ? '暂时没有授权给你的记录。' : '还没有记录。'}</p>
        {!shared && <Link className="button" to="/analyze">导入第一条记录</Link>}
      </div>}
      <div className="record-list records-archive">
        {visibleItems.map(record => <div className="record-row" key={record.id}>
          <div className="record-main">
            <span>{new Date(record.created_at).toLocaleString()}</span>
            <small className="mono">{record.id}</small>
            {shared && <span className="owner-tag">{record.owner_username ?? '已共享'}</span>}
          </div>
          <div className="record-quality">
            <QualityBadge status={record.quality_status} score={record.quality_score} />
            {record.source && <span className="badge badge-muted">{record.source}</span>}
          </div>
          <span className="record-metric">{record.duration_sec == null ? '—' : `${record.duration_sec.toFixed(1)} s`}</span>
          <span className="record-metric">{record.heart_rate_bpm == null ? '—' : `${record.heart_rate_bpm} 次/分`}</span>
          <span className="record-actions">
            <Link to={'/records/' + record.id}>查看</Link>
            {!shared && <button className="link-button" disabled={deleting === record.id}
              onClick={() => void downloadFile(`/records/${record.id}/export?format=csv`,
                `ecg-record-${record.id}.csv`).catch(caught => setError((caught as Error).message))}>
              导出
            </button>}
            {!shared && <button className="danger-link" disabled={deleting === record.id}
              onClick={() => void remove(record.id)}>{deleting === record.id ? '删除中…' : '删除'}</button>}
            {shared && <span className="badge badge-muted">只读</span>}
          </span>
        </div>)}
      </div>
      {data.pages > 1 && <div className="pager">
        <button disabled={page <= 1} onClick={() => update({page: String(page - 1)})}>上一页</button>
        <span>第 {page} / {data.pages} 页，共 {data.total} 条</span>
        <button disabled={page >= data.pages} onClick={() => update({page: String(page + 1)})}>下一页</button>
      </div>}
    </>}
  </section>;
}
