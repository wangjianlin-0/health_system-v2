import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AnalysisTask, RecordDetail as RecordDetailType, WaveformPoint, WaveformWindow,
  downloadFile, post, request,
} from '../../services/api';
import Waveform from '../../components/Waveform';
import { OutcomeBadge, OwnerTag, QualityBadge } from '../../components/badges';

function dash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function timeText(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function RecordDetail({record, onDelete, onBack, deleting}: {
  record: RecordDetailType;
  onDelete: () => void;
  onBack: () => void;
  deleting: boolean;
}) {
  const navigate = useNavigate();
  const result = record.result;
  const prediction = result.prediction;
  const quality = result.quality;
  const detail = prediction.explanation_detail;
  const owned = record.owned !== false;
  const modelMissing = prediction.status === 'model_unavailable';
  const [exporting, setExporting] = useState('');
  const [actionError, setActionError] = useState('');
  const [reanalyzing, setReanalyzing] = useState(false);
  const [note, setNote] = useState(record.note ?? '');
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteMessage, setNoteMessage] = useState('');
  const duration = result.duration_sec ?? 0;
  const [windowStart, setWindowStart] = useState(0);
  const [windowEnd, setWindowEnd] = useState(duration);
  const [windowPoints, setWindowPoints] = useState<WaveformPoint[] | null>(null);
  const [windowLoading, setWindowLoading] = useState(false);

  useEffect(() => {
    setNote(record.note ?? '');
    setNoteMessage('');
  }, [record.id, record.note]);

  useEffect(() => {
    setWindowPoints(null);
    setWindowStart(0);
    setWindowEnd(record.result.duration_sec ?? 0);
  }, [record.id, record.result.duration_sec]);

  async function exportAs(format: 'csv' | 'json') {
    setExporting(format);
    setActionError('');
    try {
      await downloadFile(`/records/${record.id}/export?format=${format}`,
        `ecg-record-${record.id}.${format}`);
    } catch (caught) {
      setActionError((caught as Error).message);
    } finally {
      setExporting('');
    }
  }

  async function downloadRaw() {
    setExporting('raw');
    setActionError('');
    try {
      await downloadFile(`/records/${record.id}/raw`, `ecg-record-${record.id}-raw.csv`);
    } catch (caught) {
      setActionError((caught as Error).message);
    } finally {
      setExporting('');
    }
  }

  async function reanalyze() {
    setReanalyzing(true);
    setActionError('');
    try {
      const task = await post<AnalysisTask>(`/records/${record.id}/reanalyze`);
      navigate('/analyze?task=' + task.id);
    } catch (caught) {
      setActionError((caught as Error).message);
    } finally {
      setReanalyzing(false);
    }
  }

  async function saveNote() {
    setNoteSaving(true);
    setNoteMessage('');
    setActionError('');
    try {
      const updated = await request<RecordDetailType>(`/records/${record.id}`, {
        method: 'PATCH',
        body: JSON.stringify({note}),
      });
      setNote(updated.note ?? '');
      setNoteMessage('备注已保存');
    } catch (caught) {
      setActionError((caught as Error).message);
    } finally {
      setNoteSaving(false);
    }
  }

  async function loadWindow() {
    const start = Math.max(0, Math.min(windowStart, duration));
    const end = Math.min(duration, Math.max(windowEnd, start + 0.01));
    if (duration <= 0 || end <= start) {
      setActionError('波形窗口无效：结束时间必须大于开始时间');
      return;
    }
    setWindowLoading(true);
    setActionError('');
    try {
      const data = await request<WaveformWindow>(
        `/records/${record.id}/waveform?start_sec=${start}&end_sec=${end}&max_points=1200`);
      setWindowPoints(data.points);
      setWindowStart(data.start_sec);
      setWindowEnd(data.end_sec);
    } catch (caught) {
      setActionError((caught as Error).message);
    } finally {
      setWindowLoading(false);
    }
  }

  function resetWindow() {
    setWindowPoints(null);
    setWindowStart(0);
    setWindowEnd(duration);
  }

  const bpm = prediction.heart_rate?.bpm ?? record.heart_rate_bpm ?? null;
  const metadata: [string, string][] = [
    ['记录 ID', record.id],
    ['任务 ID', dash(record.task_id)],
    ['来源', dash(record.source)],
    ['导联', dash(record.lead)],
    ['单位', dash(record.unit)],
    ['采样率', record.sample_rate_hz == null ? '—' : `${record.sample_rate_hz} Hz`],
    ['时长', record.duration_sec == null ? '—' : `${record.duration_sec.toFixed(2)} s`],
    ['点数', dash(record.n_samples)],
    ['处理版本', dash(record.processing_version)],
    ['模型版本', dash(record.model_version)],
    ['结果状态', prediction.status],
  ];

  return <article className="record-detail">
    <header className="detail-head">
      <div>
        <p className="eyebrow">记录详情</p>
        <h1>{timeText(record.created_at)}</h1>
        <p className="detail-sub">
          <QualityBadge status={record.quality_status ?? quality.status} score={record.quality_score ?? quality.score} />
          <OutcomeBadge outcome={prediction.status} />
          <OwnerTag name={record.owner_username} />
        </p>
      </div>
      <div className="actions detail-actions">
        <button className="secondary" disabled={Boolean(exporting)} onClick={() => void exportAs('csv')}>
          {exporting === 'csv' ? '导出中…' : '导出 CSV'}
        </button>
        <button className="secondary" disabled={Boolean(exporting)} onClick={() => void exportAs('json')}>
          {exporting === 'json' ? '导出中…' : '导出 JSON'}
        </button>
        {owned && record.has_raw_file &&
          <button className="secondary" disabled={Boolean(exporting)} onClick={() => void downloadRaw()}>
            {exporting === 'raw' ? '下载中…' : '下载原件'}
          </button>}
        {owned && <button className="secondary" disabled={reanalyzing} onClick={() => void reanalyze()}>
          {reanalyzing ? '提交中…' : '重新分析'}
        </button>}
        {owned && <button className="danger" disabled={deleting} onClick={onDelete}>删除记录</button>}
        <button className="secondary" onClick={onBack}>返回列表</button>
      </div>
    </header>
    {actionError && <p className="notice notice-error" role="alert">{actionError}</p>}
    {!owned && <p className="notice">这条记录由 {record.owner_username ?? '其他用户'} 共享，仅可查看。</p>}
    {record.supersedes_record_id &&
      <p className="hint">由记录 <Link to={'/records/' + record.supersedes_record_id}>
        {record.supersedes_record_id}</Link> 重新分析得到。</p>}

    <dl className="meta-grid">
      {metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="mono-sm">{value}</dd></div>)}
    </dl>

    <div className="wave-toolbar">
      <span>波形窗口</span>
      <label className="inline">开始
        <input type="number" min={0} max={duration} step={0.5} value={windowStart}
               onChange={event => setWindowStart(Number(event.target.value))} />
      </label>
      <label className="inline">结束
        <input type="number" min={0} max={duration} step={0.5} value={windowEnd}
               onChange={event => setWindowEnd(Number(event.target.value))} />
      </label>
      <button className="secondary" disabled={windowLoading || duration <= 0}
              onClick={() => void loadWindow()}>
        {windowLoading ? '加载中…' : '查看窗口'}
      </button>
      {windowPoints && <button className="secondary" onClick={resetWindow}>显示全部</button>}
      <span className="hint">
        {windowPoints
          ? `当前 ${windowStart.toFixed(2)}–${windowEnd.toFixed(2)} s，${windowPoints.length} 点`
          : `完整记录 0–${duration.toFixed(2)} s`}
      </span>
    </div>

    <Waveform values={windowPoints ? undefined : result.waveform ?? []}
              points={windowPoints ?? undefined}
              duration={windowPoints ? windowEnd - windowStart : duration}
              offset={windowPoints ? windowStart : 0}
              unit={result.unit ?? 'mV'} />

    <div className="result-grid">
      <section>
        <h2>信号质量</h2>
        <p><QualityBadge status={quality.status} score={quality.score} /></p>
        <p className="hint">{quality.scope}</p>
        {quality.reasons?.length > 0 && <ul>{quality.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
      </section>
      <section>
        <h2>分类结果</h2>
        <p>{prediction.label ? prediction.label : '未产生标签'}</p>
        <p className="hint">置信度：{prediction.confidence == null ? '—' : `${(prediction.confidence * 100).toFixed(0)}%`}</p>
        <p className="hint">模型版本：{dash(record.model_version)}</p>
      </section>
      <section>
        <h2>心率</h2>
        <p>{bpm == null ? '—' : `${bpm} 次/分`}</p>
        <p className="hint">节律：{prediction.heart_rate?.regularity ?? '—'}</p>
        {prediction.heart_rate && (prediction.heart_rate.min_bpm != null || prediction.heart_rate.max_bpm != null) &&
          <p className="hint">范围：{prediction.heart_rate.min_bpm ?? '—'}–{prediction.heart_rate.max_bpm ?? '—'} 次/分</p>}
      </section>
      <section>
        <h2>心拍统计</h2>
        <p>共 {prediction.beats?.count ?? '—'} 个心拍</p>
        <p className="hint">室性早搏：{prediction.beats?.vpc_count ?? 0} 次</p>
      </section>
    </div>

    {modelMissing && <div className="notice notice-info">
      <strong>本次只完成了信号检查，没有做 AI 分类。</strong>
      <p>{prediction.explanation || '当前后端没有加载分类模型，未产生标签、心率和心拍统计。'}</p>
      <p className="hint">
        常见原因是运行环境没有安装模型依赖，或输入不满足模型要求（例如 OpenECG 需要 500 Hz、至少 10 秒）。
        这不是信号质量问题，也不一定需要重新测量；换到带模型的运行环境后可以点“重新分析”重跑。
      </p>
    </div>}
    {!modelMissing && prediction.status === 'skipped_quality' &&
      <p className="notice">信号质量不足，本次未做分类。{prediction.explanation}</p>}
    {!modelMissing && prediction.status !== 'skipped_quality' && !prediction.label &&
      <p className="notice">{prediction.explanation || '本记录未产生分类结论。'}</p>}

    {detail && !modelMissing && <section className="explanation">
      <h2>解读</h2>
      {detail.elderly_summary && <p className="elderly">{detail.elderly_summary}</p>}
      {detail.professional_interpretation && <p>{detail.professional_interpretation}</p>}
      {detail.evidence?.length ? <><h3>分析依据</h3><ul>{detail.evidence.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      {detail.uncertainty?.length ? <><h3>不确定说明</h3><ul>{detail.uncertainty.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      {detail.next_steps?.length ? <><h3>下一步建议</h3><ul>{detail.next_steps.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      {detail.provider && <small>解释引擎：{detail.provider === 'deepseek' ? 'DeepSeek 大模型' : '本地模板'}</small>}
    </section>}

    {owned ? <section className="note-editor">
      <h2>我的备注</h2>
      <textarea value={note} maxLength={500} rows={3} placeholder="例如：测量时间、服药情况、当时感受"
                onChange={event => {setNote(event.target.value); setNoteMessage('');}} />
      <div className="actions">
        <button className="secondary" disabled={noteSaving} onClick={() => void saveNote()}>
          {noteSaving ? '保存中…' : '保存备注'}
        </button>
        <span className="hint">{noteMessage || `最多 500 字符，当前 ${note.length}`}</span>
      </div>
    </section> : record.note ? <section className="explanation">
      <h2>备注</h2>
      <p>{record.note}</p>
    </section> : null}

    <footer className="disclaimer">
      本页为课程研究用途的辅助记录，不构成医疗诊断。分析结果与处理版本：{dash(record.processing_version)}。
    </footer>
  </article>;
}
