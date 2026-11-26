import { useEffect, useMemo, useState } from 'react';
import BodyContextForm from './BodyContextForm';
import EcgImageExport from './EcgImageExport';
import { Link, useNavigate } from 'react-router-dom';
import {
  AnalysisTask, BeatEvent, RecordDetail as RecordDetailType,
  downloadFile, post, request,
} from '../../services/api';
import Waveform from '../../components/Waveform';
import { OutcomeBadge, OwnerTag, QualityBadge } from '../../components/badges';

const waveformRanges = [
  {length: 10, label: '10s'},
  {length: 30, label: '30s'},
  {length: 'all', label: '全程'},
] as const;

function dash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function timeText(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function rrFromSavedBeats(events: BeatEvent[], sampleRateHz: number) {
  const times = new Set<number>();
  for (const event of events) {
    if (event.time_sec != null && Number.isFinite(event.time_sec)) {
      times.add(event.time_sec);
    } else if (event.sample != null && Number.isFinite(event.sample) && sampleRateHz > 0) {
      times.add(event.sample / sampleRateHz);
    }
  }
  const ordered = [...times].sort((first, second) => first - second);
  const intervals = ordered.slice(1).map((time, index) => time - ordered[index]);
  if (!intervals.length) return null;

  const mean = intervals.reduce((sum, interval) => sum + interval, 0) / intervals.length;
  const variance = intervals.reduce((sum, interval) => sum + (interval - mean) ** 2, 0) / intervals.length;
  // Use the same RR variability rule as RPeakDetector._result for older reports.
  const rrCv = Math.round(Math.sqrt(variance) / mean * 1000) / 1000;
  return {
    rrMeanMs: Math.round(mean * 10000) / 10,
    regularity: intervals.length < 2 ? undefined : rrCv > 0.2 ? 'irregular' : 'regular',
  };
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
  const beatAnalysis = result.beat_analysis;
  const rhythmAnalysis = result.rhythm_analysis;
  const rateAnalysis = result.rate_analysis;
  const peakHeartRate = result.r_peak_analysis?.heart_rate;
  const reportedRr = rateAnalysis?.rr_mean_ms ?? prediction.heart_rate?.rr_mean_ms ?? peakHeartRate?.rr_mean_ms;
  const reportedRegularity = rateAnalysis?.regularity ?? prediction.heart_rate?.regularity ?? peakHeartRate?.regularity;
  const hasRegularity = reportedRegularity === 'regular' || reportedRegularity === 'irregular';
  const savedBeats = beatAnalysis?.source === 'openecg_fallback' ? beatAnalysis.events : undefined;
  const legacyRr = useMemo(() => {
    if (!savedBeats?.length || quality.status === 'insufficient' || (reportedRr != null && hasRegularity)) return null;
    return rrFromSavedBeats(savedBeats, result.sample_rate_hz);
  }, [savedBeats, quality.status, reportedRr, hasRegularity, result.sample_rate_hz]);
  const rrMeanMs = reportedRr ?? legacyRr?.rrMeanMs;
  const regularity = hasRegularity ? reportedRegularity : legacyRr?.regularity;
  const regularityText = regularity === 'regular' ? '相对规则' :
    regularity === 'irregular' ? '不规则' : '无法判断';
  const respirationAnalysis = result.respiration_analysis;
  const safety = result.safety;
  const qualityReasonLabels: Record<string, string> = {
    record_too_short: '记录时长过短',
    empty_signal: '没有检测到有效信号',
    flatline: '波形存在较长平直片段',
    lead_off_suspected: '疑似电极脱落或接触不良',
    status_frame_abnormal: '采集设备状态帧异常',
    rpeak_detection_unreliable: '心拍定位结果不一致',
  };
  const qualityReasons = [...(quality.reasons ?? [])];
  if (quality.status === 'insufficient' && qualityReasons.length === 0) {
    for (const code of quality.reason_codes ?? []) {
      if (qualityReasonLabels[code]) qualityReasons.push(qualityReasonLabels[code]);
    }
  }
  const visibleQualityWarnings = quality.status === 'insufficient'
    ? qualityReasons
    : quality.warnings ?? [];
  const owned = record.owned !== false;
  const rhythmClassified = rhythmAnalysis?.status === 'classified' || prediction.rhythm_model?.status === 'classified';
  const modelMissing = prediction.status === 'model_unavailable' && !rhythmClassified;
  const [exporting, setExporting] = useState('');
  const [imageExport, setImageExport] = useState(false);
  const [actionError, setActionError] = useState('');
  const [reanalyzing, setReanalyzing] = useState(false);
  const [nextModel, setNextModel] = useState('');
  const [note, setNote] = useState(record.note ?? '');
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteMessage, setNoteMessage] = useState('');
  const duration = result.duration_sec ?? 0;
  const [windowLength, setWindowLength] = useState<10 | 30 | 'all'>(10);
  const [windowStart, setWindowStart] = useState(0);
  const [selectedAbnormal, setSelectedAbnormal] = useState<number | null>(null);
  const [detailTab, setDetailTab] = useState<'overview' | 'models' | 'notes'>('overview');

  useEffect(() => {
    setWindowStart(0);
    setWindowLength(10);
    setSelectedAbnormal(null);
  }, [record.id]);

  useEffect(() => {
    setNote(record.note ?? '');
    setNoteMessage('');
  }, [record.id, record.note]);

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
      const task = await post<AnalysisTask>(`/records/${record.id}/reanalyze`, nextModel ? {model_type: nextModel} : {});
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

  const bpm = prediction.heart_rate?.bpm ?? record.heart_rate_bpm ?? null;
  const beatCounts = beatAnalysis?.counts ?? prediction.beats?.by_type ?? {};
  const beatModelVersion = beatAnalysis?.model_version ?? prediction.model_version ?? record.model_version ?? '';
  const usesMergedVfClass = /^hgb/i.test(beatModelVersion);
  const ventricularCode = usesMergedVfClass ? 'VF' : 'V';
  const normalBeats = beatCounts.normal ?? beatCounts.N ?? 0;
  const atrialBeats = beatCounts.pac ?? beatCounts.S ?? 0;
  const ventricularBeats = beatCounts.pvc ?? beatCounts.vpc ?? beatCounts[ventricularCode] ?? prediction.beats?.vpc_count ?? 0;
  const fusionBeats = beatCounts.fusion ?? beatCounts.F ?? 0;
  const beatTotal = beatAnalysis?.total ?? prediction.beats?.count ?? 0;
  const beatClasses = [
    {code: 'N', count: normalBeats},
    {code: 'S', count: atrialBeats},
    {code: ventricularCode, count: ventricularBeats},
  ];
  if (!usesMergedVfClass) beatClasses.push({code: 'F', count: fusionBeats});
  const displayLength = windowLength === 'all' ? duration : Math.min(duration, windowLength);
  const maxWindowStart = Math.max(0, duration - displayLength);
  const windowEnd = Math.min(duration, windowStart + displayLength);
  const sampleStart = Math.max(0, Math.floor(windowStart * result.sample_rate_hz));
  const sampleEnd = Math.min(result.waveform?.length ?? 0, Math.ceil(windowEnd * result.sample_rate_hz));
  const displayedWaveform = (result.waveform ?? []).slice(sampleStart, sampleEnd);
  const sourceEvents: BeatEvent[] = beatAnalysis?.events ?? (prediction.beats?.items ?? []).map(item => ({
    time_sec: item.r_seconds, sample: item.r_sample500, label: item.label,
  }));
  const beatMarkers = sourceEvents.flatMap(event => {
    const time = event.time_sec ?? (event.sample != null ? event.sample / result.sample_rate_hz : null);
    if (time == null || !Number.isFinite(time)) return [];
    const label = event.label.toUpperCase();
    const normal = label === 'N' || label.includes('NORMAL');
    return [{time_sec: time, label: normal ? 'N' : event.label, kind: normal ? 'normal' as const : 'attention' as const}];
  });
  const orderedBeatMarkers = [...beatMarkers].sort((first, second) => first.time_sec - second.time_sec);
  const abnormalRows = orderedBeatMarkers.flatMap((event, index) => {
    if (event.kind !== 'attention') return [];
    const previous = orderedBeatMarkers[index - 1];
    const rrMs = previous ? Math.round((event.time_sec - previous.time_sec) * 1000) : null;
    const aamiLabel = event.label === 'V' ? 'V · 室性早搏' : event.label === 'S' ? 'S · 室上性早搏' : event.label;
    return [{...event, number: index + 1, rrMs, bpm: rrMs && rrMs > 0 ? Math.round(60_000 / rrMs) : null, aamiLabel}];
  });
  function locateAbnormal(index: number) {
    setSelectedAbnormal(index);
    setWindowLength(10);
    setWindowStart(Math.max(0, Math.min(duration - 10, abnormalRows[index].time_sec - 5)));
    setDetailTab('overview');
  }

  function jumpToAbnormal(direction: -1 | 1) {
    const current = selectedAbnormal ?? (direction === 1 ? -1 : 0);
    locateAbnormal((current + direction + abnormalRows.length) % abnormalRows.length);
  }
  const miniStep = Math.max(1, Math.ceil((result.waveform?.length ?? 0) / 900));
  const miniWaveform = (result.waveform ?? []).filter((_, index) => index % miniStep === 0)
    .map((value, index, values) => `${(index / Math.max(values.length - 1, 1) * 1000).toFixed(1)},${(28 - value * 12).toFixed(1)}`).join(' ');
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

  return <article className="record-detail analysis-detail-page">
    {imageExport && <EcgImageExport record={record} start={0}
      end={duration} onClose={() => setImageExport(false)} />}
    <header className="detail-head analysis-detail-head">
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
        <button disabled={!result.waveform?.length} onClick={() => setImageExport(true)}>导出心电图片</button>
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
        {owned && <select aria-label="重新分析使用的模型" value={nextModel} onChange={event => setNextModel(event.target.value)}>
          <option value="">沿用原模型</option><option value="cnn">CNN H27</option><option value="hgb">HGB v92</option><option value="ensemble">CNN + HGB复核</option>
          <option value="openecg">OpenECG</option><option value="none">仅信号检查</option>
        </select>}
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

    {owned && !record.supersedes_record_id && <BodyContextForm key={record.id} id={record.id}
      context={record.body_context} />}

    <dl className="meta-grid">
      {metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="mono-sm">{value}</dd></div>)}
    </dl>

    <div className="analysis-result-cards">
      <div className="analysis-result-primary-row">
      <article className={ventricularBeats > 0 ? 'analysis-result-risk' : 'analysis-result-calm'}>
        <span>{ventricularBeats > 0 ? '模型筛查提示 · 需结合症状评估' : '模型筛查结果'}</span>
        <strong>{ventricularBeats > 0
          ? `${usesMergedVfClass ? 'VF 合并类' : '室性早搏'}标记 ${ventricularBeats} 拍`
          : prediction.label ?? '未产生分类结论'}</strong>
        <p>{ventricularBeats > 0 && beatTotal > 0
          ? `逐拍分类标记占本次检测心拍的 ${(ventricularBeats / beatTotal * 100).toFixed(1)}%。模型标记不等同于临床诊断。`
          : prediction.explanation || '模型输出用于辅助回顾，不构成临床诊断。'}</p>
      </article>
      <article className="analysis-result-rate">
        <span>平均心率 <small>参考 60–100</small></span>
        <strong>{bpm == null ? '—' : bpm} <small>次/分</small></strong>
        <p>节律 {regularityText}{rrMeanMs != null ? ` · RR ${Math.round(rrMeanMs)} ms` : ''}</p>
      </article>
      <article className="analysis-result-beats"><span>心拍分类分布 · 共 {beatTotal} 拍</span>
        <div className="analysis-class-bar" aria-hidden="true">
          {beatClasses.map(({code, count}) =>
            <i key={code} style={{width: `${count / Math.max(beatTotal, 1) * 100}%`}} />)}
        </div>
        <div className="analysis-beat-counts">
          {beatClasses.map(({code, count}) => <strong key={code}><span>{code}</span><b>{count}</b></strong>)}
        </div>
        <p>分类计数仅适用于本次信号与所选模型</p></article>
      </div>
      <div className="analysis-result-secondary-row">
      {rhythmAnalysis && <article className="analysis-result-model">
        <span>整段节律 · OpenECG</span><strong>{rhythmAnalysis.primary}</strong>
        <p>{rhythmAnalysis.confidence == null ? '未提供置信度' : `置信度 ${(rhythmAnalysis.confidence * 100).toFixed(0)}%`} · {rhythmAnalysis.model_version ?? 'OpenECG'}</p>
      </article>}
      {respirationAnalysis && <article className="analysis-result-model">
        <span>呼吸阻抗</span><strong>{respirationAnalysis.rate_bpm == null ? '未获得呼吸率' : `${respirationAnalysis.rate_bpm} 次/分`}</strong>
        <p>{respirationAnalysis.cycle_count ?? 0} 个周期 · 长间隔 {respirationAnalysis.pause_candidates.length}</p>
      </article>}
      <article className={`analysis-result-quality-card ${quality.status === 'insufficient' ? 'analysis-result-quality-fail' : ''}`}>
        <span>信号质量 <QualityBadge status={quality.status} /></span>
        <strong>{quality.score == null ? '—' : `${quality.score.toFixed(1)} / 100`}</strong>
        <p>{quality.grade ?? quality.status}{quality.metrics?.snr?.db != null ? ` · SNR ${quality.metrics.snr.db.toFixed(1)} dB` : ''}</p>
        {(visibleQualityWarnings.length > 0 || quality.status === 'insufficient') && <details className="quality-reason-details">
          <summary>{quality.status === 'insufficient' ? '查看未通过原因' : `查看质量提示（${visibleQualityWarnings.length}）`}</summary>
          <div className="quality-reason-list">
            <b>{quality.status === 'insufficient' ? '检测原因' : '质量提示'}</b>
            {visibleQualityWarnings.length > 0
              ? <ul>{visibleQualityWarnings.map((reason, index) => <li key={`${reason}-${index}`}>{reason}</li>)}</ul>
              : <p>未返回具体原因，请检查信号波形和采集设备。</p>}
            {quality.status === 'insufficient' && <p className="quality-retry-guidance">
              {quality.guidance?.[0] ?? '请检查电极贴合和设备连接，保持静止后重新测量。'}
            </p>}
          </div>
        </details>}
      </article>
      </div>
    </div>

    <div className="analysis-detail-tabs" role="tablist" aria-label="分析详情分页">
      <button role="tab" aria-selected={detailTab === 'overview'} className={detailTab === 'overview' ? 'selected' : ''}
              onClick={() => setDetailTab('overview')}>波形与核心指标</button>
      <button role="tab" aria-selected={detailTab === 'models'} className={detailTab === 'models' ? 'selected' : ''}
              onClick={() => setDetailTab('models')}>模型与风险详情{abnormalRows.length ? `（${abnormalRows.length}）` : ''}</button>
      <button role="tab" aria-selected={detailTab === 'notes'} className={detailTab === 'notes' ? 'selected' : ''}
              onClick={() => setDetailTab('notes')}>解读与备注</button>
    </div>

    {detailTab === 'overview' && <div className="analysis-wave-column analysis-wave-review">
      <div className="analysis-wave-heading"><div><h2>心电波形审阅</h2><span>{duration.toFixed(2)} 秒 · {record.sample_rate_hz} Hz · {result.unit ?? 'mV'}</span></div>
        <div className="analysis-range-buttons" role="group" aria-label="波形时间范围">
          {waveformRanges.map(({length, label}) => <button key={length}
            aria-pressed={windowLength === length}
            className={windowLength === length ? 'selected' : ''} onClick={() => {
              setWindowLength(length);
              setWindowStart(length === 'all' ? 0 : Math.min(windowStart, Math.max(0, duration - length)));
            }}>{label}</button>)}
        </div>
      </div>
      {abnormalRows.length > 0 && <div className="analysis-abnormal-nav">
        <span>异常心拍（{abnormalRows.length}）</span>
        <button className="secondary" onClick={() => jumpToAbnormal(-1)} aria-label="上一个异常心拍">‹</button>
        <button className="secondary" onClick={() => jumpToAbnormal(1)}>定位下一个 →</button>
        <small>{selectedAbnormal == null ? '—' : selectedAbnormal + 1} / {abnormalRows.length}</small>
      </div>}
      <p className="analysis-window-caption">窗口 {windowStart.toFixed(1)}–{windowEnd.toFixed(1)} 秒 · 红色标记为非 N 类逐拍结果</p>
      <Waveform values={displayedWaveform} duration={Math.max(windowEnd - windowStart, 0.01)}
        offset={windowStart} unit={result.unit ?? 'mV'} markers={beatMarkers} />
      <div className="analysis-minimap-wrap">
        <div className="analysis-minimap">
          <svg viewBox="0 0 1000 56" preserveAspectRatio="none" aria-hidden="true">
            <polyline points={miniWaveform} fill="none" stroke="#91a2b8" strokeWidth="1.2" />
            {abnormalRows.map((marker, index) => <line key={`${marker.time_sec}-${index}`}
              x1={duration ? marker.time_sec / duration * 1000 : 0} x2={duration ? marker.time_sec / duration * 1000 : 0}
              y1="3" y2="53" className="analysis-minimap-event" />)}
            <rect x={duration ? windowStart / duration * 1000 : 0} y="2"
              width={duration ? Math.max(8, (windowEnd - windowStart) / duration * 1000) : 0} height="52"
              className="analysis-minimap-window" />
          </svg>
        </div>
        <input type="range" min={0} max={maxWindowStart} step={Math.max(0.05, duration / 1000)} value={Math.min(windowStart, maxWindowStart)}
          disabled={maxWindowStart === 0} onChange={event => setWindowStart(Number(event.target.value))} aria-label="拖动浏览心电全程" />
        <div className="analysis-minimap-labels"><span>0 秒</span><span>{duration.toFixed(0)} 秒</span></div>
      </div>
    </div>}

    {detailTab === 'models' && <div className="analysis-tab-content">
      <div className="analysis-model-layout">
        <section className="analysis-event-panel">
          <div className="analysis-panel-heading"><div><h2>异常心拍事件清单</h2><p>点击事件可切换到波形页并定位时间</p></div>
            <strong>{abnormalRows.length} 项</strong></div>
          {abnormalRows.length ? <div className="analysis-event-table-wrap"><table className="analysis-event-table">
            <thead><tr><th>序号</th><th>发生时间</th><th>AAMI 分类</th><th>RR 间期</th><th>瞬时心率</th><th>定位</th></tr></thead>
            <tbody>{abnormalRows.map((event, index) => <tr key={`${event.number}-${event.time_sec}`}>
              <td>#{event.number}</td><td>{event.time_sec.toFixed(2)} s</td>
              <td className={event.label === 'V' ? 'event-v' : 'event-s'}>{event.aamiLabel}</td>
              <td>{event.rrMs == null ? '—' : `${event.rrMs} ms`}</td>
              <td>{event.bpm == null ? '—' : `${event.bpm} BPM`}</td>
              <td><button className="analysis-locate-button" onClick={() => locateAbnormal(index)}>查看波形 →</button></td>
            </tr>)}</tbody>
          </table></div> : <p className="analysis-empty-events">当前没有可显示的异常心拍事件。</p>}
        </section>
        <section className="analysis-metadata-panel">
          <h2>采集参数与技术元数据</h2>
          <dl>{metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        </section>
      </div>
      <details className="analysis-model-extra">
        <summary>查看模型计算与风险规则详情</summary>
        {(beatAnalysis || rhythmAnalysis || rateAnalysis || respirationAnalysis || safety) &&
          <section className="multimodel-panel">
            <p className="eyebrow">多模型联合分析</p><h2>OpenECG 节律 + CNN/HGB 心拍</h2>
            <div className="analysis-card-grid">
              {rhythmAnalysis && <article className="analysis-card"><span className="analysis-kicker">整段节律 · OpenECG</span><strong>{rhythmAnalysis.primary}</strong>
                <p>置信度：{rhythmAnalysis.confidence == null ? '—' : `${(rhythmAnalysis.confidence * 100).toFixed(0)}%`}</p><p>模型：{rhythmAnalysis.model_version ?? '—'}</p></article>}
              {beatAnalysis && <article className="analysis-card"><span className="analysis-kicker">逐心拍 · {beatAnalysis.source}</span><strong>{beatAnalysis.total} 个心拍</strong>
                <p>{beatClasses.map(({code, count}) => `${code} ${count}`).join(' · ')}</p><p>状态：{beatAnalysis.status}</p></article>}
              {rateAnalysis && <article className="analysis-card"><span className="analysis-kicker">心率与 RR</span><strong>{rateAnalysis.average_bpm == null ? '未获得' : `${rateAnalysis.average_bpm} 次/分`}</strong>
                <p>规则性：{regularityText}</p><p>平均 RR：{rrMeanMs == null ? '—' : `${rrMeanMs} ms`}</p></article>}
              {respirationAnalysis && <article className="analysis-card"><span className="analysis-kicker">呼吸阻抗</span><strong>{respirationAnalysis.rate_bpm == null ? '未获得呼吸率' : `${respirationAnalysis.rate_bpm} 次/分`}</strong>
                <p>分析器：{respirationAnalysis.provider}</p><p>周期 {respirationAnalysis.cycle_count ?? 0} · 长间隔 {respirationAnalysis.pause_candidates.length}</p></article>}
              {safety && <article className={`analysis-card safety-${safety.level}`}><span className="analysis-kicker">固定安全规则</span><strong>{safety.level}</strong><p>{safety.message}</p></article>}
            </div>
            {beatAnalysis?.limitations?.map(item => <p className="hint" key={item}>{item}</p>)}
          </section>}
        {modelMissing && <p className="notice notice-info"><strong>本次只完成信号检查，没有做 AI 分类。</strong> {prediction.explanation}</p>}
        {!modelMissing && rhythmClassified && beatAnalysis?.status === 'model_unavailable' && <p className="notice notice-info">已完成 OpenECG 节律分析，本次未进行 CNN/HGB 逐拍分类。</p>}
        {!modelMissing && prediction.status === 'skipped_quality' && <p className="notice">信号质量不足，本次未做分类。{prediction.explanation}</p>}
        {!modelMissing && prediction.status !== 'skipped_quality' && !prediction.label && <p className="notice">{prediction.explanation || '本记录未产生分类结论。'}</p>}
      </details>
    </div>}

    {detailTab === 'notes' && <div className="analysis-tab-content analysis-notes-layout">
      <div className="care-advice-grid">
        <section><h2>长辈当下照护要点</h2><ul>
          <li>先静坐或半卧位休息 15 分钟，避免急起急走与劳累。</li>
          <li>暂时停饮浓茶、咖啡，保持情绪平稳、呼吸均匀。</li>
          <li>若持续胸闷、眼前发黑或气短，请尽快告知家属并及时就医。</li>
        </ul></section>
        <section><h2>日常预防与随访建议</h2><ul>
          <li>保持规律睡眠，按医嘱服用降压及其他慢病药物。</li>
          <li>可在晨起或睡前静息时测量并记录，持续观察个人变化。</li>
          <li>就诊时可提供心电图片、逐拍 CSV 和当时的身体感受。</li>
        </ul></section>
        <p className="care-followup"><span aria-hidden="true">◷</span> 复测时机：静坐休息约 15 分钟后再测，并按医生建议安排随访。</p>
      </div>
      {detail && !modelMissing && <section className="explanation analysis-interpretation-card">
      <div className="analysis-notes-heading"><div><span>AI 辅助解读</span><h2>本次记录说明</h2></div>
        {detail.provider && <span className="analysis-provider">{detail.provider === 'deepseek' ? 'DeepSeek' : '本地模板'}</span>}
      </div>
      {detail.elderly_summary && <div className="plain-summary">
        <span>先看结论</span><p>{detail.elderly_summary}</p>
      </div>}
      {detail.professional_interpretation && <><h3>专业解释</h3><p>{detail.professional_interpretation}</p></>}
      {detail.condition_education?.length ? <div className="condition-education">
        <h3>异常相关知识</h3>
        <p className="hint">以下是一般医学科普，不表示本次记录已经证明相应症状或病因。</p>
        {detail.condition_education.map(item => <article key={item.condition}>
          <h4>{item.condition}</h4><p>{item.what_it_means}</p>
          <strong>可能伴随的感受</strong><ul>{item.possible_symptoms.map(value => <li key={value}>{value}</li>)}</ul>
          <strong>常见相关因素</strong><ul>{item.common_associations.map(value => <li key={value}>{value}</li>)}</ul>
          <strong>何时需要就医</strong><ul>{item.when_to_seek_care.map(value => <li key={value}>{value}</li>)}</ul>
        </article>)}
      </div> : null}
      {detail.evidence?.length ? <><h3>分析依据</h3><ul>{detail.evidence.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      {detail.uncertainty?.length ? <><h3>不确定说明</h3><ul>{detail.uncertainty.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      {detail.next_steps?.length ? <><h3>下一步建议</h3><ul>{detail.next_steps.map(item => <li key={item}>{item}</li>)}</ul></> : null}
    </section>}

    {owned ? <section className="note-editor analysis-personal-note">
      <div className="analysis-notes-heading"><div><span>个人补充</span><h2>测量备注</h2></div>
        <span className="analysis-note-count">{note.length} / 500</span></div>
      <textarea value={note} maxLength={500} rows={3} placeholder="例如：测量时间、服药情况、当时感受"
                onChange={event => {setNote(event.target.value); setNoteMessage('');}} />
      <div className="actions">
        <button className="secondary" disabled={noteSaving} onClick={() => void saveNote()}>
          {noteSaving ? '保存中…' : '保存备注'}
        </button>
        <span className="hint" role="status">{noteMessage || '备注仅用于个人记录与复诊回顾。'}</span>
      </div>
    </section> : record.note ? <section className="explanation">
      <h2>备注</h2>
      <p>{record.note}</p>
    </section> : null}
    </div>}

    <footer className="disclaimer">
      本页为课程研究用途的辅助记录，不构成医疗诊断。分析结果与处理版本：{dash(record.processing_version)}。
    </footer>
  </article>;
}
