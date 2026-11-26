import { useEffect, useMemo, useRef, useState } from 'react';
import BodyContextForm, {formatBodyContext} from './BodyContextForm';
import EcgImageExport from './EcgImageExport';
import { Link, useNavigate } from 'react-router-dom';
import {
  AnalysisTask, BeatEvent, RecordDetail as RecordDetailType,
  downloadFile, post, recordSourceLabel, request,
} from '../../services/api';
import Waveform from '../../components/Waveform';
import { OutcomeBadge, OwnerTag, QualityBadge } from '../../components/badges';
import './recordReview.css';

const beatCodes: Record<string, string> = {
  normal: 'N', pac: 'S', pvc: 'V', fusion: 'F', unknown: '未分类',
  unclassified: '未分类', paced: '起搏',
};

export function modelDisplay(version?: string | null, requested?: string | null): string {
  const value = (version || requested || '').toLowerCase();
  if (requested === 'ensemble' || value.includes('ensemble') || value.includes('primary+hgb')) return 'CNN + HGB 复核';
  if (value.includes('openecg')) return 'OpenECG';
  if (value.includes('hgb')) return 'HGB v92';
  if (value.includes('cnn')) return 'CNN H27';
  if (value === 'none' || value.includes('signal')) return '仅信号检查';
  return '未获得模型结果';
}

function eventTime(event: BeatEvent, sampleRate: number) {
  return event.time_sec ?? (event.sample != null && sampleRate > 0 ? event.sample / sampleRate : null);
}

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
  const [detailTab, setDetailTab] = useState<'overview' | 'models' | 'notes'>('overview');
  const [filtered, setFiltered] = useState(false);
  const [selectedAbnormal, setSelectedAbnormal] = useState<number | null>(null);
  const [beatLimit, setBeatLimit] = useState(30);
  const [title, setTitle] = useState(record.title);
  const [savedTitle, setSavedTitle] = useState(record.title);
  const [titleMessage, setTitleMessage] = useState('');
  const [titleSaving, setTitleSaving] = useState(false);
  const waveHeading = useRef<HTMLHeadingElement>(null);
  const scrollToWave = useRef(false);

  useEffect(() => {
    setWindowStart(0);
    setWindowLength(10);
    setFiltered(false);
    setSelectedAbnormal(null);
    setDetailTab('overview');
    setBeatLimit(30);
    setTitle(record.title);
    setSavedTitle(record.title);
    setTitleMessage('');
  }, [record.id, record.title]);

  useEffect(() => {
    if (detailTab === 'overview' && scrollToWave.current) {
      scrollToWave.current = false;
      waveHeading.current?.focus();
    }
  }, [detailTab]);

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

  async function saveTitle() {
    setTitleSaving(true);
    setTitleMessage('');
    try {
      const next = await request<RecordDetailType>(`/records/${record.id}/title`, {
        method: 'PATCH', body: JSON.stringify({title}),
      });
      setTitle(next.title);
      setSavedTitle(next.title);
      setTitleMessage('记录名称已保存');
    } catch (caught) {
      setTitleMessage((caught as Error).message);
    } finally {setTitleSaving(false);}
  }

  const bpm = prediction.heart_rate?.bpm ?? record.heart_rate_bpm ?? null;
  const beatCounts = beatAnalysis?.counts ?? prediction.beats?.by_type ?? {};
  const normalBeats = beatCounts.normal ?? beatCounts.N ?? 0;
  const atrialBeats = beatCounts.pac ?? beatCounts.S ?? 0;
  const ventricularBeats = prediction.beats?.vpc_count ?? beatCounts.pvc ?? beatCounts.V ?? 0;
  const fusionBeats = beatCounts.fusion ?? beatCounts.F ?? 0;
  const isHgb = /^hgb/i.test(beatAnalysis?.model_version ?? record.model_version ?? '');
  const unknownBeats = beatCounts.unknown ?? prediction.beats?.unclassified_count ?? 0;
  const displayLength = windowLength === 'all' ? duration : Math.min(duration, windowLength);
  const maxWindowStart = Math.max(0, duration - displayLength);
  const windowEnd = Math.min(duration, windowStart + displayLength);
  const sampleStart = Math.max(0, Math.floor(windowStart * result.sample_rate_hz));
  const sampleEnd = Math.min(result.waveform?.length ?? 0, Math.ceil(windowEnd * result.sample_rate_hz));
  const displayedWaveform = (filtered ? result.waveform_processed_mV ?? [] : result.waveform ?? []).slice(sampleStart, sampleEnd);
  const sourceEvents: BeatEvent[] = beatAnalysis?.events ?? (prediction.beats?.items ?? []).map(item => ({
    time_sec: item.r_seconds, sample: item.r_sample500, label: item.valid ? item.label : 'unknown',
    confidence: item.confidence, raw_label: item.label,
  }));
  const classified = beatAnalysis ? beatAnalysis.status === 'classified' : prediction.status === 'classified';
  const orderedBeatMarkers = sourceEvents.flatMap(event => {
    const time = eventTime(event, result.sample_rate_hz);
    if (time == null || !Number.isFinite(time) || time < 0 || time > duration) return [];
    const label = (isHgb && event.label === 'pvc') ? 'VF' : (beatCodes[event.label.toLowerCase()] ?? event.label);
    const attention = classified && label !== 'N';
    return [{time_sec: time, label, confidence: event.confidence,
      kind: attention ? 'attention' as const : 'normal' as const}];
  }).sort((first, second) => first.time_sec - second.time_sec);
  const abnormalRows = orderedBeatMarkers.flatMap((event, index) => {
    if (event.kind !== 'attention') return [];
    const previous = orderedBeatMarkers[index - 1];
    const seconds = previous ? event.time_sec - previous.time_sec : 0;
    const rrMs = seconds > 0 ? Math.round(seconds * 1000) : null;
    return [{...event, number: index + 1, rrMs, bpm: seconds > 0 ? Math.round(60 / seconds) : null}];
  });
  const beatMarkers = classified ? orderedBeatMarkers : [];
  function locateAbnormal(index: number) {
    if (!abnormalRows[index]) return;
    setSelectedAbnormal(index);
    setWindowLength(10);
    setWindowStart(Math.max(0, Math.min(duration - 10, abnormalRows[index].time_sec - 5)));
    if (detailTab !== 'overview') {
      scrollToWave.current = true;
      setDetailTab('overview');
    }
  }
  function jumpToAbnormal(direction: 1 | -1) {
    const total = abnormalRows.length;
    const index = selectedAbnormal == null ? (direction === 1 ? 0 : total - 1)
      : (selectedAbnormal + direction + total) % total;
    locateAbnormal(index);
  }
  const miniWaveform = useMemo(() => {
    const samples = result.waveform ?? [];
    const step = Math.max(1, Math.ceil(samples.length / 900));
    const summary = samples.filter((_, index) => index % step === 0);
    const min = Math.min(...summary);
    const range = Math.max(...summary) - min || 1;
    return summary.map((value, index) => {
      const x = index * step / Math.max(samples.length - 1, 1) * 1000;
      return `${x.toFixed(1)},${(49 - (value - min) / range * 42).toFixed(1)}`;
    }).join(' ');
  }, [result.waveform]);
  const metadata: [string, string][] = [
    ['记录 ID', record.id],
    ['任务 ID', dash(record.task_id)],
    ['来源', recordSourceLabel(record.source)],
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
        <h1>{savedTitle || timeText(record.created_at)}</h1>
        <p className="hint review-record-source">{timeText(record.created_at)} · {modelDisplay(record.model_version, prediction.beat_model?.requested)}</p>
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
      <p className="hint">由 <Link to={'/records/' + (record.root_record_id ?? record.supersedes_record_id)}>
        {record.root_record_title ?? '原测量记录'}</Link> 重新分析得到。</p>}
    {safety && safety.level !== 'reference_only' && <p className={`notice ${safety.urgent ? 'notice-error' : ''}`}
      role={safety.urgent ? 'alert' : undefined}>{safety.message}</p>}

    <div className="analysis-result-cards">
      <div className="analysis-result-primary-row">
      <article className={ventricularBeats > 0 ? 'analysis-result-risk' : 'analysis-result-calm'}>
        <span>{ventricularBeats > 0 ? '模型筛查提示 · 需结合症状评估' : '模型筛查结果'}</span>
        <strong>{ventricularBeats > 0 ? `${isHgb ? 'VF 合并类' : 'V 类'}标记 ${ventricularBeats} 拍` : prediction.label ?? '未产生分类结论'}</strong>
        <p>{ventricularBeats > 0 ? '可在事件清单中定位波形，供回顾与沟通。' : prediction.explanation || '模型输出用于辅助回顾。'}</p>
      </article>
      <article className="analysis-result-beats"><span>心拍分类分布 · 共 {beatAnalysis?.total ?? prediction.beats?.count ?? 0} 拍</span>
        <div className="analysis-class-bar" aria-label={`正常 ${normalBeats}，S 类 ${atrialBeats}，V 类 ${ventricularBeats}，融合 ${fusionBeats}`}>
          <i style={{width: `${normalBeats / Math.max(beatAnalysis?.total ?? prediction.beats?.count ?? 1, 1) * 100}%`}} />
          <i style={{width: `${atrialBeats / Math.max(beatAnalysis?.total ?? prediction.beats?.count ?? 1, 1) * 100}%`}} />
          <i style={{width: `${ventricularBeats / Math.max(beatAnalysis?.total ?? prediction.beats?.count ?? 1, 1) * 100}%`}} />
          <i style={{width: `${fusionBeats / Math.max(beatAnalysis?.total ?? prediction.beats?.count ?? 1, 1) * 100}%`}} />
        </div>
        <div className="analysis-beat-counts" aria-label={`N ${normalBeats}，S ${atrialBeats}，V ${ventricularBeats}，F ${fusionBeats}`}>
          <strong><span>N</span><b>{normalBeats}</b></strong>
          <strong><span>S</span><b>{atrialBeats}</b></strong>
          <strong><span>{isHgb ? 'VF' : 'V'}</span><b>{ventricularBeats}</b></strong>
          {!isHgb && <strong><span>F</span><b>{fusionBeats}</b></strong>}
        </div>
        <p>{unknownBeats > 0 ? `未分类 ${unknownBeats} 拍 · ` : ''}分类计数仅适用于本次信号与所选模型</p></article>
      <article className="analysis-result-rate"><span>平均心率 <small>参考 60–100</small></span><strong>{bpm == null ? '—' : bpm} <small>次/分</small></strong>
        <p>节律 {regularityText}{rrMeanMs != null ? ` · RR ${Math.round(rrMeanMs)} ms` : ''}</p></article>
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
      <div className="analysis-wave-heading"><div><h2 ref={waveHeading} tabIndex={-1}>心电波形审阅</h2><span>{duration.toFixed(2)} 秒 · {record.sample_rate_hz} Hz · {result.unit ?? 'mV'}</span></div>
        <div className="review-wave-controls">
        <div className="analysis-range-buttons" role="group" aria-label="波形类型">
          <button aria-pressed={!filtered} className={!filtered ? 'selected' : ''} onClick={() => setFiltered(false)}>原始</button>
          <button aria-pressed={filtered} className={filtered ? 'selected' : ''} disabled={!result.waveform_processed_mV?.length}
            onClick={() => setFiltered(true)}>滤波</button>
        </div>
        <div className="analysis-range-buttons" role="group" aria-label="波形时间范围">
          {([10, 30, 'all'] as const).map(length => <button key={length} aria-pressed={windowLength === length}
            className={windowLength === length ? 'selected' : ''} onClick={() => {
              setWindowLength(length);
              setWindowStart(length === 'all' ? 0 : Math.min(windowStart, Math.max(0, duration - length)));
              setSelectedAbnormal(null);
            }}>{length === 'all' ? '全程' : `${length}s`}</button>)}
        </div>
        </div>
      </div>
      {abnormalRows.length > 0 && <div className="analysis-abnormal-nav">
        <span>事件复核（{abnormalRows.length}）</span>
        <button className="secondary" onClick={() => jumpToAbnormal(-1)} aria-label="上一个异常心拍">‹</button>
        <button className="secondary" onClick={() => jumpToAbnormal(1)}>定位下一个 →</button>
        <small aria-live="polite">{selectedAbnormal != null
          ? `已定位 ${abnormalRows[selectedAbnormal]?.time_sec.toFixed(2)} 秒 · ${selectedAbnormal + 1} / ${abnormalRows.length}`
          : '可定位非 N 类和未分类心拍'}</small>
      </div>}
      <p className="analysis-window-caption">窗口 {windowStart.toFixed(2)}–{windowEnd.toFixed(2)} 秒{classified && ' · 红色标记为非 N 类或未分类心拍'}</p>
      <Waveform values={displayedWaveform} duration={Math.max(0, (displayedWaveform.length - 1) / result.sample_rate_hz)}
        offset={sampleStart / result.sample_rate_hz} unit={result.unit ?? 'mV'} markers={beatMarkers} />
      <div className="analysis-minimap-wrap">
        <div className="analysis-minimap">
          <svg viewBox="0 0 1000 56" preserveAspectRatio="none" aria-hidden="true">
            <polyline points={miniWaveform} fill="none" stroke="#91a2b8" strokeWidth="1.2" />
            {abnormalRows.map((marker, index) => <line key={`${marker.time_sec}-${index}`}
              x1={duration ? marker.time_sec / duration * 1000 : 0} x2={duration ? marker.time_sec / duration * 1000 : 0}
              y1="3" y2="53" className="analysis-minimap-event" />)}
            {duration > 0 && <rect x={windowStart / duration * 1000} y="2"
              width={(windowEnd - windowStart) / duration * 1000} height="52"
              className="analysis-minimap-window" />}
          </svg>
        </div>
        <input type="range" min={0} max={maxWindowStart} step="any" value={Math.min(windowStart, maxWindowStart)}
          disabled={maxWindowStart === 0} onChange={event => {setWindowStart(Number(event.target.value)); setSelectedAbnormal(null);}}
          onKeyDown={event => {
            const amount = ({ArrowLeft: -0.5, ArrowDown: -0.5, ArrowRight: 0.5, ArrowUp: 0.5})[event.key];
            if (amount === undefined) return;
            event.preventDefault();
            setWindowStart(value => Math.max(0, Math.min(maxWindowStart, value + amount)));
            setSelectedAbnormal(null);
          }} aria-label="拖动浏览心电全程" />
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
              <td className={event.label === 'V' || event.label === 'VF' ? 'event-v' : 'event-s'}>{event.label}</td>
              <td>{event.rrMs == null ? '—' : `${event.rrMs} ms`}</td>
              <td>{event.bpm == null ? '—' : `${event.bpm} BPM`}</td>
              <td><button className="analysis-locate-button" aria-label={`查看第 ${event.number} 拍波形`}
                onClick={() => locateAbnormal(index)}>查看波形 →</button></td>
            </tr>)}</tbody>
          </table></div> : <p className="analysis-empty-events">当前没有可显示的异常心拍事件。</p>}
        </section>
        <section className="analysis-metadata-panel">
          <h2>采集参数与技术元数据</h2>
          <dl>{metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        </section>
      </div>
      {orderedBeatMarkers.length > 0 && <details className="analysis-model-extra">
        <summary>完整逐拍结果（{orderedBeatMarkers.length}）</summary>
        <div className="analysis-event-table-wrap"><table className="analysis-event-table">
          <thead><tr><th>拍</th><th>时间</th><th>类别</th><th>模型概率</th></tr></thead>
          <tbody>{orderedBeatMarkers.slice(0, beatLimit).map((event, index) => <tr key={index}>
            <td>{index + 1}</td><td>{event.time_sec.toFixed(3)} 秒</td>
            <td>{classified ? event.label : '未分类'}</td><td>{event.confidence == null ? '—' : `${(event.confidence * 100).toFixed(1)}%`}</td>
          </tr>)}</tbody>
        </table></div>
        {beatLimit < orderedBeatMarkers.length && <button className="secondary" onClick={() => setBeatLimit(value => value + 100)}>显示更多心拍</button>}
      </details>}
      {quality.metrics && <details className="analysis-model-extra">
        <summary>查看信号质量指标</summary>
        <dl className="review-quality">
          <div><dt>基线漂移比例</dt><dd>{quality.metrics.baseline_wander?.ratio == null ? '—' : (quality.metrics.baseline_wander.ratio * 100).toFixed(1) + '%'}</dd></div>
          <div><dt>工频干扰</dt><dd>{quality.metrics.powerline_interference?.frequency_hz == null ? '—' : quality.metrics.powerline_interference.frequency_hz + ' Hz'}</dd></div>
          <div><dt>平直片段</dt><dd>{quality.metrics.flatline == null ? '—' : (quality.metrics.flatline.fraction * 100).toFixed(1) + '%'}</dd></div>
          <div><dt>导联脱落</dt><dd>{quality.metrics.lead_off == null ? '—' : quality.metrics.lead_off.suspected ? '疑似' : '未发现明显线索'}</dd></div>
          <div><dt>估算 SNR</dt><dd>{quality.metrics.snr?.db == null ? '—' : quality.metrics.snr.db.toFixed(1) + ' dB'}</dd></div>
          <div><dt>心拍一致性 bSQI</dt><dd>{quality.metrics.bsqi?.score == null ? '—' : (quality.metrics.bsqi.score * 100).toFixed(1) + '%'}</dd></div>
        </dl>
        {(quality.guidance ?? []).map(item => <p className="hint" key={item}>{item}</p>)}
      </details>}
      <details className="analysis-model-extra">
        <summary>查看模型计算与风险规则详情</summary>
        {(beatAnalysis || rhythmAnalysis || rateAnalysis || respirationAnalysis || safety) &&
          <section className="multimodel-panel">
            <p className="eyebrow">多模型联合分析</p><h2>OpenECG 节律 + CNN/HGB 心拍</h2>
            <div className="analysis-card-grid">
              {rhythmAnalysis && <article className="analysis-card"><span className="analysis-kicker">整段节律 · OpenECG</span><strong>{rhythmAnalysis.primary}</strong>
                <p>置信度：{rhythmAnalysis.confidence == null ? '—' : `${(rhythmAnalysis.confidence * 100).toFixed(0)}%`}</p><p>模型：{rhythmAnalysis.model_version ?? '—'}</p></article>}
              {beatAnalysis && <article className="analysis-card"><span className="analysis-kicker">逐心拍 · {beatAnalysis.source}</span><strong>{beatAnalysis.total} 个心拍</strong>
                <p>N {beatAnalysis.counts.normal ?? 0} · S {beatAnalysis.counts.pac ?? 0} · V {beatAnalysis.counts.pvc ?? 0} · F {beatAnalysis.counts.fusion ?? 0}</p><p>状态：{beatAnalysis.status}</p></article>}
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

    {owned && <section className="review-rename"><h2>记录名称</h2>
      <form onSubmit={event => {event.preventDefault(); void saveTitle();}}>
        <input aria-label="记录名称" value={title} maxLength={80} onChange={event => setTitle(event.target.value)} />
        <button className="secondary" disabled={titleSaving}>保存名称</button>
      </form>
      {titleMessage && <p role="status">{titleMessage}</p>}
    </section>}
    {record.root_record_id ? <section className="record-origin-note"><h2>测量时的身体状况</h2>
      <p>此记录沿用<Link to={'/records/' + record.root_record_id}>原始测量记录</Link>的测量信息。</p>
      <dl>
        <div><dt>当时在做什么</dt><dd>{formatBodyContext(record.body_context?.scene, 'scene')}</dd></div>
        <div><dt>当时的感受</dt><dd>{formatBodyContext(record.body_context?.feeling, 'feeling')}</dd></div>
      </dl>
    </section> : owned && <BodyContextForm key={record.id} id={record.id} context={record.body_context} />}
    {owned && !record.root_record_id ? <section className="note-editor analysis-personal-note">
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
