import { useEffect, useState } from 'react';
import EcgImageExport from './EcgImageExport';
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
  const elderlySummary = detail?.elderly_summary?.replace(
    '这些结果用于辅助参考，不能单独作为诊断；异常心拍较多或伴有不适时，建议保存记录并请专业人员复核。',
    '',
  );
  const beatAnalysis = result.beat_analysis;
  const beatClasses = [
    {code: 'N', label: '正常类心拍', key: 'normal'},
    {code: 'S', label: '室上性异位心拍', key: 'pac'},
    {code: 'V', label: '室性异位心拍', key: 'pvc'},
    {code: 'F', label: '融合心拍', key: 'fusion'},
  ];
  const hasBeatClassification = beatAnalysis?.status === 'classified';
  const rhythmAnalysis = result.rhythm_analysis;
  const rateAnalysis = result.rate_analysis;
  const respirationAnalysis = result.respiration_analysis;
  const safety = result.safety;
  const owned = record.owned !== false;
  const modelMissing = prediction.status === 'model_unavailable';
  const [exporting, setExporting] = useState('');
  const [imageExport, setImageExport] = useState(false);
  const [actionError, setActionError] = useState('');
  const [reanalyzing, setReanalyzing] = useState(false);
  const [nextModel, setNextModel] = useState('');
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
    {imageExport && <EcgImageExport record={record} start={windowPoints ? windowStart : 0}
      end={windowPoints ? windowEnd : duration} onClose={() => setImageExport(false)} />}
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
          <option value="">沿用原模型</option><option value="cnn">CNN H27</option><option value="hgb">HGB v92</option>
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
        {quality.grade && <p>质量等级：<strong>{quality.grade}</strong></p>}
        {quality.metrics && <div className="quality-metrics">
          <span>基线漂移：{quality.metrics.baseline_wander?.level ?? 'unknown'}
            {quality.metrics.baseline_wander?.ratio != null ? ` (${(quality.metrics.baseline_wander.ratio * 100).toFixed(1)}%)` : ''}</span>
          <span>工频干扰：{quality.metrics.powerline_interference?.level ?? 'unknown'}
            {quality.metrics.powerline_interference?.frequency_hz ? ` (${quality.metrics.powerline_interference.frequency_hz} Hz)` : ''}</span>
          <span>运动伪差：{quality.metrics.motion_artifact?.level ?? 'unknown'}</span>
          <span>平直片段：{quality.metrics.flatline ? `${(quality.metrics.flatline.fraction * 100).toFixed(1)}%` : 'unknown'}</span>
          <span>导联脱落：{quality.metrics.lead_off?.suspected ? '疑似' : '未发现明显线索'}</span>
          <span>状态帧：{quality.metrics.status_frame?.available
            ? `${quality.metrics.status_frame.abnormal_count}/${quality.metrics.status_frame.count} 异常` : '未提供'}</span>
          <span>估算 SNR：{quality.metrics.snr?.db != null ? `${quality.metrics.snr.db.toFixed(1)} dB` : 'unknown'}</span>
          <span>心拍一致性 bSQI：{quality.metrics.bsqi?.score != null
            ? `${(quality.metrics.bsqi.score * 100).toFixed(1)}% · ${quality.metrics.bsqi.level}` : 'unknown'}</span>
        </div>}
        {quality.warnings && quality.warnings.length > 0 &&
          <ul>{quality.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>}
        {quality.guidance && quality.guidance.length > 0 &&
          <ul className="quality-guidance">{quality.guidance.map(item => <li key={item}>{item}</li>)}</ul>}
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
        {prediction.beats?.vpc_count != null && <p className="hint">室性早搏：{prediction.beats.vpc_count} 次</p>}
      </section>
    </div>

    {beatAnalysis && <section className="beat-classification-panel" aria-label="心拍分类 NSVF">
      <p className="eyebrow">独立指标 · 心拍分类</p>
      <div className="beat-classification-heading">
        <h2>心拍分类 · N / S / V / F</h2>
        <span className="hint">共检测 {beatAnalysis.total} 个心拍</span>
      </div>
      <dl className="beat-classification-grid">
        {beatClasses.map(item => <div key={item.code}>
          <dt><span className="beat-class-code">{item.code}</span>{item.label}</dt>
          <dd>{hasBeatClassification ? beatAnalysis.counts[item.key] ?? 0 : '—'}<span>个</span></dd>
        </div>)}
      </dl>
      {!hasBeatClassification && <p className="hint">本次未获得 NSVF 分类结果。</p>}
    </section>}

    {(rhythmAnalysis || rateAnalysis || respirationAnalysis || safety) &&
      <section className="multimodel-panel">
        <p className="eyebrow">多模型联合分析</p>
        <h2>节律、心率与呼吸</h2>
        <div className="analysis-card-grid">
          {rhythmAnalysis && <article className="analysis-card">
            <span className="analysis-kicker">整段节律 · OpenECG</span>
            <strong>{rhythmAnalysis.primary}</strong>
            <p>置信度：{rhythmAnalysis.confidence == null ? '—' : `${(rhythmAnalysis.confidence * 100).toFixed(0)}%`}</p>
            <p>模型：{rhythmAnalysis.model_version ?? '—'}</p>
          </article>}
          {rateAnalysis && <article className="analysis-card">
            <span className="analysis-kicker">心率与 RR</span>
            <strong>{rateAnalysis.average_bpm == null ? '未获得' : `${rateAnalysis.average_bpm} 次/分`}</strong>
            <p>规则性：{rateAnalysis.regularity ?? '无法判断'}</p>
            <p>RR：{rateAnalysis.rr_mean_ms == null ? '—' : `${rateAnalysis.rr_mean_ms} ms`}</p>
          </article>}
          {respirationAnalysis && <article className="analysis-card">
            <span className="analysis-kicker">呼吸阻抗</span>
            <strong>{respirationAnalysis.rate_bpm == null ? '未获得呼吸率' : `${respirationAnalysis.rate_bpm} 次/分`}</strong>
            <p>分析器：{respirationAnalysis.provider}</p>
            <p>周期 {respirationAnalysis.cycle_count ?? 0} · 长间隔 {respirationAnalysis.pause_candidates.length}</p>
          </article>}
          {safety && <article className={`analysis-card safety-${safety.level}`}>
            <span className="analysis-kicker">固定安全规则</span>
            <strong>{safety.level}</strong>
            {!['本次结果可作为参考；如有不适仍应咨询专业人员。',
              '建议保存记录并结合症状咨询专业人员。'].includes(safety.message) && <p>{safety.message}</p>}
          </article>}
        </div>
      </section>}
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

  </article>;
}
