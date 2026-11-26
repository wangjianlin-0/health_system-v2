import { useEffect, useMemo, useState } from 'react';
import './recordDetail.css';
import BodyContextForm, {formatBodyContext} from './BodyContextForm';
import EcgImageExport from './EcgImageExport';
import { Link, useNavigate } from 'react-router-dom';
import {
  AnalysisTask, RecordDetail as RecordDetailType,
  downloadFile, post, recordSourceLabel, request,
} from '../../services/api';
import Waveform from '../../components/Waveform';
import { OutcomeBadge, OwnerTag, QualityBadge } from '../../components/badges';

export function modelDisplay(version?: string | null, requested?: string | null): string {
  const value = (version || requested || '').toLowerCase();
  if (value.includes('ensemble')) return 'CNN + HGB 复核';
  if (value.includes('openecg')) return 'OpenECG';
  if (value.includes('hgb')) return 'HGB v92';
  if (value.includes('cnn')) return 'CNN H27';
  if (value === 'none' || value.includes('signal')) return '仅信号检查';
  return '未获得模型结果';
}

function dash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function readable(value?: string | null): string {
  const labels: Record<string, string> = {good: '良好', fair: '一般', poor: '较差', high: '较高', low: '较低', moderate: '中等', unknown: '无法判断', regular: '较规则', irregular: '不规则', sinus: '窦性节律', afib: '房颤相关类别', afl: '房扑相关类别', ventricular: '室性节律类别', paced: '起搏节律类别', other: '其他节律类别', reference_only: '仅供参考', needs_review: '建议复核', repeat_measurement: '建议复测', urgent_symptoms: '及时就医'};
  return value ? labels[value] ?? value : '未提供';
}

function timeText(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function rrFromSavedBeats(events: NonNullable<RecordDetailType['result']['beat_analysis']>['events'],
                          sampleRateHz: number) {
  const times = new Set<number>();
  for (const event of events) {
    if (event.time_sec != null && Number.isFinite(event.time_sec)) times.add(event.time_sec);
    else if (event.sample != null && Number.isFinite(event.sample) && sampleRateHz > 0) {
      times.add(event.sample / sampleRateHz);
    }
  }
  const ordered = [...times].sort((first, second) => first - second);
  const intervals = ordered.slice(1).map((time, index) => time - ordered[index]);
  if (!intervals.length) return null;
  const mean = intervals.reduce((sum, interval) => sum + interval, 0) / intervals.length;
  const variance = intervals.reduce((sum, interval) => sum + (interval - mean) ** 2, 0) / intervals.length;
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
  const elderlySummary = detail?.elderly_summary?.replace(
    '这些结果用于辅助参考，不能单独作为诊断；异常心拍较多或伴有不适时，建议保存记录并请专业人员复核。',
    '',
  );
  const beatAnalysis = result.beat_analysis;
  const hgb = /hgb/i.test(beatAnalysis?.model_version ?? record.model_version ?? '');
  const beatClasses = [
    {code: 'N', label: '正常类心拍', key: 'normal'},
    {code: 'S', label: '室上性异位心拍', key: 'pac'},
    {code: hgb ? 'VF' : 'V', label: hgb ? 'V / E / F 合并类' : '室性异位心拍', key: 'pvc'},
    ...(!hgb ? [{code: 'F', label: '融合心拍', key: 'fusion'}] : []),
    ...((beatAnalysis?.counts.paced ?? 0) > 0 ? [{code: 'P', label: '起搏心拍', key: 'paced'}] : []),
    {code: '?', label: '未分类心拍', key: 'unknown'},
  ];
  const hasBeatClassification = beatAnalysis?.status === 'classified';
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
  const respirationAnalysis = result.respiration_analysis;
  const safety = result.safety;
  const owned = record.owned !== false;
  const rhythmClassified = rhythmAnalysis?.status === 'classified' || prediction.rhythm_model?.status === 'classified';
  const modelMissing = prediction.status === 'model_unavailable' && !rhythmClassified;
  const [exporting, setExporting] = useState('');
  const [imageExport, setImageExport] = useState(false);
  const [actionError, setActionError] = useState('');
  const [reanalyzing, setReanalyzing] = useState(false);
  const [nextModel, setNextModel] = useState('');
  const [page, setPage] = useState<'summary' | 'beats' | 'quality' | 'notes'>('summary');
  const [note, setNote] = useState(record.note ?? '');
  const [title, setTitle] = useState(record.title);
  const [titleSaving, setTitleSaving] = useState(false);
  const [titleMessage, setTitleMessage] = useState('');
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteMessage, setNoteMessage] = useState('');
  const duration = result.duration_sec ?? 0;
  const [windowStart, setWindowStart] = useState(0);
  const [windowEnd, setWindowEnd] = useState(Math.min(10, duration));
  const [appliedWindow, setAppliedWindow] = useState({start: 0, end: Math.min(10, duration)});
  const [filtered, setFiltered] = useState(false);
  const [beatLimit, setBeatLimit] = useState(30);

  useEffect(() => {
    setPage('summary');
    setNote(record.note ?? '');
    setNoteMessage('');
    setTitle(record.title);
    setTitleMessage('');
  }, [record.id, record.note]);

  useEffect(() => {
    const end = Math.min(10, record.result.duration_sec ?? 0);
    setWindowStart(0);
    setWindowEnd(end);
    setAppliedWindow({start: 0, end});
    setFiltered(false);
    setBeatLimit(30);
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
      const task = await post<AnalysisTask>(`/records/${record.id}/reanalyze`, nextModel ? {model_type: nextModel} : {});
      navigate('/analyze?task=' + task.id);
    } catch (caught) {
      setActionError((caught as Error).message);
    } finally {
      setReanalyzing(false);
    }
  }

  async function saveTitle() {
    setTitleSaving(true);
    setTitleMessage('');
    try {
      const updated = await request<RecordDetailType>('/records/' + record.id + '/title', {
        method: 'PATCH', body: JSON.stringify({title}),
      });
      setTitle(updated.title);
      setTitleMessage('名称已保存');
    } catch (caught) {
      setTitleMessage((caught as Error).message);
    } finally {
      setTitleSaving(false);
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

  function loadWindow() {
    const start = Math.max(0, Math.min(windowStart, duration));
    const end = Math.min(duration, windowEnd);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      setActionError('波形窗口无效：结束时间必须大于开始时间');
      return;
    }
    setActionError('');
    setWindowStart(start); setWindowEnd(end); setAppliedWindow({start, end});
  }

  function resetWindow() {
    setActionError(''); setWindowStart(0); setWindowEnd(duration);
    setAppliedWindow({start: 0, end: duration});
  }

  const sourceValues = (filtered ? result.waveform_processed_mV : result.waveform) ?? [];
  const sampleRate = result.sample_rate_hz;
  const startSample = Math.floor(appliedWindow.start * sampleRate);
  const endSample = Math.min(sourceValues.length, Math.ceil(appliedWindow.end * sampleRate));
  const visibleValues = sourceValues.slice(startSample, endSample);
  const unknownCount = beatAnalysis?.counts.unknown ?? 0;
  const classifiedCount = Object.entries(beatAnalysis?.counts ?? {})
    .reduce((sum, [key, count]) => sum + (key === 'unknown' ? 0 : count), 0);
  const className = (key: string) => beatClasses.find(item => item.key === key)?.label ?? key;
  const rhythmAvailable = rhythmAnalysis?.status === 'classified';
  const respirationAvailable = respirationAnalysis?.rate_bpm != null;
  const bpm = prediction.heart_rate?.bpm ?? record.heart_rate_bpm ?? null;
  const metadata: [string, string][] = [
    ['记录名称', title],
    ['来源', recordSourceLabel(record.source)],
    ['导联', record.lead === 'user_single_lead' ? '单导联' : dash(record.lead)],
    ['单位', dash(record.unit)],
    ['采样率', record.sample_rate_hz == null ? '—' : `${record.sample_rate_hz} Hz`],
    ['时长', record.duration_sec == null ? '—' : `${record.duration_sec.toFixed(2)} s`],
    ['点数', dash(record.n_samples)],
    ['处理版本', dash(record.processing_version)],
    ['模型版本', dash(record.model_version)],
    ['结果状态', prediction.status === 'classified' ? '已分类' : prediction.status === 'model_unavailable' ? '未获得分类' : prediction.status],
  ];
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

  return <article className="record-detail record-redesign">
    {imageExport && <EcgImageExport record={record} start={appliedWindow.start}
      end={appliedWindow.end} onClose={() => setImageExport(false)} />}
    <div className="record-top-actions"><button className="record-back" type="button" onClick={onBack}>← 返回记录列表</button>
      {owned && <button className="record-delete-icon" type="button" disabled={deleting} onClick={onDelete}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v6m4-6v6" /></svg>删除记录</button>}
    </div>
    <header className="record-hero">
      <div className="record-heading">
        <p className="eyebrow">ECG / 心电记录</p>
        <h1>{title}</h1>
        {owned && <div className="record-rename">
          <label>修改记录名称<input maxLength={80} value={title} onChange={event => setTitle(event.target.value)}
            placeholder="留空则恢复默认名称" /></label>
          <button className="secondary" disabled={titleSaving} onClick={() => void saveTitle()}>保存名称</button>
          <span role="status">{titleMessage}</span>
        </div>}
        <p className="record-date">{timeText(record.created_at)} <span>·</span> {duration.toFixed(2)} 秒 <span>·</span> {result.sample_rate_hz} Hz <span>·</span> 分析模型：{modelDisplay(record.model_version, prediction.beat_model?.requested)}</p>
      </div>
      <div className="record-primary-actions">
        <button disabled={!result.waveform?.length} onClick={() => setImageExport(true)}>导出心电图片</button>
        <details className="record-more">
          <summary>更多操作 <span aria-hidden="true">⌄</span></summary>
          <div className="record-more-menu">
            <button disabled={Boolean(exporting)} onClick={() => void exportAs('csv')}>{exporting === 'csv' ? '导出中…' : '导出 CSV'}</button>
            <button disabled={Boolean(exporting)} onClick={() => void exportAs('json')}>{exporting === 'json' ? '导出中…' : '导出 JSON'}</button>
            {owned && record.has_raw_file && <button disabled={Boolean(exporting)} onClick={() => void downloadRaw()}>{exporting === 'raw' ? '下载中…' : '下载原件'}</button>}
            {owned && <><label>重新分析使用的模型<select value={nextModel} onChange={event => setNextModel(event.target.value)}>
              <option value="">沿用原模型</option><option value="cnn">CNN H27</option><option value="hgb">HGB v92</option><option value="openecg">OpenECG</option><option value="none">仅信号检查</option>
            </select></label>
            <Link className="record-model-guide" to="/guide#guide-models">如何选择分析模型？</Link>
            <button disabled={reanalyzing} onClick={() => void reanalyze()}>{reanalyzing ? '提交中…' : '重新分析'}</button></>}

          </div>
        </details>
      </div>
    </header>
    {actionError && <p className="notice notice-error" role="alert">{actionError}</p>}
    {!owned && <p className="notice">这条记录由 {record.owner_username ?? '其他用户'} 共享，仅可查看。</p>}
    <nav className="record-section-tabs" aria-label="记录详情分段">
      <button type="button" className={page === 'summary' ? 'selected' : ''} onClick={() => setPage('summary')}>测量概览与波形</button>
      <button type="button" className={page === 'beats' ? 'selected' : ''} onClick={() => setPage('beats')}>心拍与节律</button>
      <button type="button" className={page === 'quality' ? 'selected' : ''} onClick={() => setPage('quality')}>质量与解读</button>
      <button type="button" className={page === 'notes' ? 'selected' : ''} onClick={() => setPage('notes')}>状况与备注</button>
    </nav>
    <div hidden={page !== 'summary'}>
    <div className="record-status">
      <OutcomeBadge outcome={prediction.status} />
      <QualityBadge status={quality.status} />
      <span className="record-model">{beatAnalysis?.model_version ?? record.model_version ?? '未加载分类模型'}</span>
    </div>
    <p className="record-summary">{hasBeatClassification
      ? `已完成 ${classifiedCount} 拍分类，${unknownCount} 拍未分类，可结合原始波形复核。`
      : '已保存心电记录，请结合信号质量与分析状态查看结果。'}</p>
    {safety && safety.level !== 'reference_only' && <div className={`notice ${safety.urgent ? 'notice-error' : ''}`} role="status"><strong>{readable(safety.level)}</strong><p>{safety.message}</p>{safety.reasons?.length > 0 && <ul>{safety.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}</div>}
    <dl className="record-metrics">
      <div><dt>估算心率</dt><dd>{bpm == null ? '—' : Number(bpm.toFixed(2))}<span>次/分</span></dd><small>基于本次心电信号估算</small></div>
      <div><dt>检测心拍</dt><dd>{beatAnalysis?.total ?? prediction.beats?.count ?? '—'}<span>拍</span></dd><small>{hasBeatClassification ? `${classifiedCount} 拍已分类 · ${unknownCount} 拍未分类` : '分类状态见下方说明'}</small></div>
      <div><dt>信号质量</dt><dd>{quality.score ?? '—'}<span>分</span></dd><small>工程评分 · 不等同临床有效性</small></div>
      <div><dt>心律规则性</dt><dd>{readable(regularity)}<span>{rrMeanMs == null ? '' : ' · ' + Math.round(rrMeanMs) + ' ms'}</span></dd><small>RR 间期辅助统计</small></div>
    </dl>

    <section className="record-wave-panel" aria-label="真实心电波形">
      <div className="record-panel-head"><div><p className="eyebrow">SIGNAL / 原始记录</p><h2>心电波形</h2></div>
        <div className="wave-switch" role="group" aria-label="波形类型">
          <button className={!filtered ? 'selected' : ''} aria-pressed={!filtered} onClick={() => setFiltered(false)}>原始波形</button>
          <button className={filtered ? 'selected' : ''} aria-pressed={filtered} disabled={!result.waveform_processed_mV?.length} onClick={() => setFiltered(true)}>滤波波形</button>
        </div>
      </div>
      <Waveform values={visibleValues} duration={Math.max(0, (visibleValues.length - 1) / sampleRate)} offset={startSample / sampleRate} unit={result.unit ?? 'mV'} />
      <div className="wave-toolbar">
        <label className="inline">开始 / 秒<input aria-label="波形开始秒数" type="number" min={0} max={duration} step={0.5} value={windowStart} onChange={event => setWindowStart(Number(event.target.value))} /></label>
        <label className="inline">结束 / 秒<input aria-label="波形结束秒数" type="number" min={0} max={duration} step={0.5} value={windowEnd} onChange={event => setWindowEnd(Number(event.target.value))} /></label>
        <button className="secondary" disabled={duration <= 0} onClick={loadWindow}>查看窗口</button>
        <button className="record-text-button" onClick={resetWindow}>显示全部</button>
      </div>
      <p className="record-wave-note">{filtered ? '离线节律滤波用于辅助观察，原始数据保留，可随时切换。' : '来自本次上传记录，可切换滤波波形对照查看。'}</p>
    </section>

    </div>
    <div hidden={page !== 'beats'}>
    {beatAnalysis && <section className="record-beats" aria-label="心拍分类">
      <div className="record-panel-head"><div><p className="eyebrow">BEATS / 逐拍分析</p><h2>心拍分类</h2></div><span className="hint">共 {beatAnalysis.total} 拍</span></div>
      <dl className="record-beat-grid">{beatClasses.map(item => <div key={item.key} className={item.key === 'unknown' ? 'unclassified' : ''}>
        <dt><span className="beat-class-code">{item.code}</span>{item.label}</dt><dd>{hasBeatClassification ? beatAnalysis.counts[item.key] ?? 0 : '—'}<span>拍</span></dd>
      </div>)}</dl>
      <p className="hint">{hasBeatClassification ? '心拍类别为模型输出，不代表整段心电正常或疾病诊断。未分类心拍不自动计入正常类。' : '本次未获得心拍分类结果。'}</p>
      {beatAnalysis.events?.length > 0 && <div className="beat-events"><h3>逐拍结果 · {beatAnalysis.events.length} 条</h3>
        <div className="beat-table-scroll"><table><thead><tr><th>序号</th><th>时间 / 秒</th><th>类别</th><th>模型概率</th><th>原始标签</th></tr></thead><tbody>{beatAnalysis.events.slice(0, beatLimit).map((event, index) => <tr key={index}><td>{index + 1}</td><td>{event.time_sec?.toFixed(3) ?? '—'}</td><td>{className(event.label)}</td><td>{event.confidence == null ? '未提供' : `${(event.confidence * 100).toFixed(1)}%`}</td><td>{event.raw_label ?? '—'}</td></tr>)}</tbody></table></div>
        <p className="hint">模型概率是单个心拍类别的输出概率，不是诊断准确率。</p>
        {beatLimit < beatAnalysis.events.length && <button className="secondary" onClick={() => setBeatLimit(value => value + 100)}>显示更多心拍</button>}
      </div>}
      {beatAnalysis.limitations?.length ? <div className="beat-events"><h3>模型适用范围</h3><ul>{beatAnalysis.limitations.map(item => <li key={item}>{item}</li>)}</ul></div> : null}
    </section>}

    </div>
    <div hidden={page !== 'quality'}>
    <section className="record-disclosure"><h2>信号质量与心率细节 · {readable(quality.grade)}</h2><div className="disclosure-body">
        {quality.grade && <p>质量等级：<strong>{readable(quality.grade)}</strong></p>}
        {quality.metrics && <div className="quality-metrics">
          <span>基线漂移：{readable(quality.metrics.baseline_wander?.level)}
            {quality.metrics.baseline_wander?.ratio != null ? ` (${(quality.metrics.baseline_wander.ratio * 100).toFixed(1)}%)` : ''}</span>
          <span>工频干扰：{readable(quality.metrics.powerline_interference?.level)}
            {quality.metrics.powerline_interference?.frequency_hz ? ` (${quality.metrics.powerline_interference.frequency_hz} Hz)` : ''}</span>
          <span>运动伪差：{readable(quality.metrics.motion_artifact?.level)}</span>
          <span>平直片段：{quality.metrics.flatline ? `${(quality.metrics.flatline.fraction * 100).toFixed(1)}%` : '未提供'}</span>
          <span>导联脱落：{quality.metrics.lead_off?.suspected ? '疑似' : '未发现明显线索'}</span>
          <span>状态帧：{quality.metrics.status_frame?.available
            ? `${quality.metrics.status_frame.abnormal_count}/${quality.metrics.status_frame.count} 异常` : '未提供'}</span>
          <span>估算 SNR：{quality.metrics.snr?.db != null ? `${quality.metrics.snr.db.toFixed(1)} dB` : '未提供'}</span>
          <span>心拍一致性 bSQI：{quality.metrics.bsqi?.score != null
            ? `${(quality.metrics.bsqi.score * 100).toFixed(1)}% · ${readable(quality.metrics.bsqi.level)}` : '未提供'}</span>
        </div>}
        {visibleQualityWarnings.length > 0 &&
          <ul>{visibleQualityWarnings.map((warning, index) => <li key={warning + '-' + index}>{warning}</li>)}</ul>}
        {quality.guidance && quality.guidance.length > 0 &&
          <ul className="quality-guidance">{quality.guidance.map(item => <li key={item}>{item}</li>)}</ul>}
        {quality.reasons?.length > 0 && <ul>{quality.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}

      {rateAnalysis && <p>估算心率范围：{rateAnalysis.min_bpm ?? '—'}–{rateAnalysis.max_bpm ?? '—'} 次/分；RR 平均间期：{rrMeanMs ?? '—'} ms；规则性：{readable(regularity)}。</p>}
      <p className="hint">通过基础检查仅表示满足当前工程规则，不代表医疗设备验证或诊断结论。</p>
    </div></section>
    <div className="record-availability">
      <span>整段节律分析 <strong>{rhythmAvailable ? readable(rhythmAnalysis?.primary) : '未获得结果'}</strong></span>
      <span>呼吸分析 <strong>{respirationAvailable ? `${respirationAnalysis?.rate_bpm} 次/分` : '未获得结果'}</strong></span>
      {(rhythmAnalysis || respirationAnalysis) && <details><summary>查看可用性说明</summary>
        <p>{rhythmAvailable ? `节律模型：${rhythmAnalysis?.model_version ?? '未提供版本'}` : '整段节律结果未生成，请在技术参数中核对模型配置。心拍分类与整段节律为独立任务。'}</p>
        {rhythmAvailable && rhythmAnalysis?.confidence != null && <p>整段节律模型概率：{(rhythmAnalysis.confidence * 100).toFixed(1)}%</p>}
        <p>{respirationAvailable ? `呼吸分析器：${respirationAnalysis?.provider}；周期 ${respirationAnalysis?.cycle_count ?? 0}；长间隔 ${respirationAnalysis?.pause_candidates.length ?? 0}。` : respirationAnalysis?.fallback_reason ?? '未产生呼吸率；请确认输入是否提供呼吸通道及分析器是否可用。'}</p>
      </details>}
    </div>
    <section className="record-disclosure"><h2>记录来源与技术参数</h2><div className="disclosure-body">
      <OwnerTag name={record.owner_username} />
      <dl className="meta-grid">{metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="mono-sm">{value}</dd></div>)}</dl>
      {record.supersedes_record_id && <p className="hint">由记录 <Link to={'/records/' + (record.root_record_id ?? record.supersedes_record_id)}>{record.root_record_title ?? '最初记录'}</Link> 重新分析得到；测量状况和备注以最初记录为准。</p>}
    </div></section>
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

    {detail && !modelMissing && <section className="record-disclosure explanation">
      <h2>结果解读与下一步建议</h2><div className="disclosure-body">
      {elderlySummary && <div className="plain-summary">
        <span>先看结论</span><p>{elderlySummary}</p>
      </div>}
      {detail.professional_interpretation && <><h3>专业解释</h3><p>{detail.professional_interpretation}</p></>}
      {detail.condition_education?.length ? <div className="condition-education">
        <h3>异常相关知识</h3>
        {detail.condition_education.map(item => <article key={item.condition}>
          <h4>{item.condition}</h4><p>{item.what_it_means}</p>
          <strong>可能伴随的感受</strong><ul>{item.possible_symptoms.map(value => <li key={value}>{value}</li>)}</ul>
          <strong>常见相关因素</strong><ul>{item.common_associations.map(value => <li key={value}>{value}</li>)}</ul>
          <strong>何时需要就医</strong><ul>{item.when_to_seek_care.map(value => <li key={value}>{value}</li>)}</ul>
        </article>)}
      </div> : null}
      {detail.evidence?.length ? <><h3>分析依据</h3><ul>{detail.evidence.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      {detail.next_steps?.length ? <><h3>下一步建议</h3><ul>{detail.next_steps.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      {detail.provider && <small>解释引擎：{detail.provider === 'deepseek' ? 'DeepSeek 大模型' : '本地模板'}</small>}
    </div></section>}

    </div>
    <div hidden={page !== 'notes'}>
    {record.root_record_id ? <section className="record-origin-note"><h2>测量时的身体状况</h2>
      <p>此记录沿用最初测量时填写的信息。<Link to={'/records/' + record.root_record_id}>查看并编辑最初记录 →</Link></p>
      <dl><div><dt>当时在做什么</dt><dd>{formatBodyContext(record.body_context?.scene, 'scene')}</dd></div><div><dt>当时的感受</dt><dd>{formatBodyContext(record.body_context?.feeling, 'feeling')}</dd></div></dl>
    </section> : owned && <BodyContextForm key={record.id} id={record.id} context={record.body_context} />}
    {owned && !record.root_record_id ? <section className="note-editor">
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

    </div>
  </article>;
}
