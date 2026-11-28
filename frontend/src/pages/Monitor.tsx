import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnalysisTask, Prediction, WaveformPoint, post, request } from '../services/api';
import Waveform from '../components/Waveform';

interface Capture {
  id: string; status: string; error: string | null; port: string; baud: number; format: string;
  model: string; sample_count: number; duration_sec: number; received_bytes: number;
  points: (WaveformPoint & {raw: number; respiration?: number})[]; prediction: Prediction | null;
  analysis_samples: number; analysis_pending: boolean; pending_bytes: number;
  task: AnalysisTask | null;
}
interface Port {port: string; label: string;}
const statusLabel: Record<string, string> = {running: '采集中', stopped: '已停止', error: '采集已中断',
  starting: '连接中', limit_reached: '达到记录上限'};
const beatNames: Record<string, string> = {
  N: '正常类', S: '室上性异位类', V: '室性异位类', F: '融合类', VF: '室性／融合合并类',
};

export default function Monitor() {
  const [ports, setPorts] = useState<Port[]>([]);
  const [port, setPort] = useState('');
  const [baud, setBaud] = useState(115200);
  const [format, setFormat] = useState('document_34');
  const [model, setModel] = useState('cnn');
  const [title, setTitle] = useState('');
  const [session, setSession] = useState<Capture | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [raw, setRaw] = useState(false);
  const [windowSeconds, setWindowSeconds] = useState(5);
  const [connected, setConnected] = useState(false);
  const [reload, setReload] = useState(0);
  const action = useRef(false);
  const navigate = useNavigate();
  const active = session?.status === 'running' || session?.status === 'starting';
  const unsaved = Boolean(session && !session.task && session.sample_count > 0);

  async function refreshPorts() {
    try {const data = await request<{ports: Port[]}>('/acquisition/ports'); setPorts(data.ports);}
    catch (caught) {setError((caught as Error).message);}
  }
  useEffect(() => {void refreshPorts();}, []);
  useEffect(() => {
    let disposed = false;
    let timer: number;
    async function poll() {
      try {
        const next = await request<Capture | null>('/acquisition/sessions/current');
        if (!disposed && !action.current) {setSession(next); setConnected(true);}
      } catch (caught) {
        if (!disposed) {setError((caught as Error).message); setConnected(false);}
      } finally {
        if (!disposed) timer = window.setTimeout(() => void poll(), 500);
      }
    }
    void poll();
    return () => {disposed = true; window.clearTimeout(timer);};
  }, [reload]);

  async function run(operation: () => Promise<void>) {
    action.current = true; setBusy(true); setError('');
    try {await operation();} catch (caught) {setError((caught as Error).message);}
    finally {action.current = false; setBusy(false); setReload(value => value + 1);}
  }

  const availablePoints = session?.points ?? [];
  const latestTime = availablePoints.length ? availablePoints[availablePoints.length - 1].t : 0;
  const earliestTime = availablePoints[0]?.t ?? 0;
  const visibleDuration = Math.min(windowSeconds, Math.max(0.1, latestTime - earliestTime));
  const start = Math.max(earliestTime, latestTime - visibleDuration);
  const visibleSamples = availablePoints.filter(point => point.t >= start);
  const visiblePoints = visibleSamples.map(p => ({t: p.t, v: raw ? p.raw : p.v}));
  const respirationPoints = visibleSamples.flatMap(({t, respiration}) =>
    respiration == null ? [] : [{t, v: respiration}]);
  const duration = visiblePoints.length > 1 ? visiblePoints[visiblePoints.length - 1].t - start : Math.max(visibleDuration, 0.1);
  const selectedModel = session?.model ?? model;
  const beatClasses = selectedModel === 'hgb' ? ['N', 'S', 'VF'] : ['N', 'S', 'V', 'F'];
  const beats = session?.prediction?.beats;
  const classificationStatus = session?.prediction?.status === 'model_unavailable'
    ? session.prediction.explanation
    : beats
      ? active ? '采集中 · 累计已判定心拍'
        : session?.prediction?.preview && session.analysis_pending ? '正在完成末尾心拍分析' : '本次采集累计'
      : active ? '正在等待首批可判定心拍' : '开始采集后自动统计';
  return <section className="monitor-page live-monitor-page">
    <p className="eyebrow monitor-page-eyebrow">设备连接与测量</p>
    <h1 className="monitor-page-title">实时心电监测</h1>
    <div className="monitor-heading"><div><p className="eyebrow">ADS1292R · 蓝牙采集</p>
      <h2>开始一次心电采集</h2><p>连接采集模块，在电脑上查看波形与心拍分类。</p></div>
      <span className={`capture-status ${active ? 'is-active' : ''}`} role="status">
        {connected ? session ? statusLabel[session.status] ?? session.status : '等待连接' : '服务连接中'}
      </span></div>
    <div className="monitor-steps" aria-label="采集操作步骤">
      <div><b>1 配对设备</b><span>在 Windows 蓝牙设置中配对接收器，确认电极和采集模块已连接。</span></div>
      <div><b>2 选择串口</b><span>从下方选择新出现的 COM 端口；不确定时可先断开设备，对比刷新前后的列表。</span></div>
      <div><b>3 开始并保存</b><span>点击“开始采集”，看到波形后停止，再点“保存并完整分析”。</span></div>
    </div>
    <details className="monitor-help"><summary>不知道该选哪个串口？查看详细步骤</summary>
      <p>先在 Windows 设备管理器的“端口 (COM 和 LPT)”中确认蓝牙或 USB 接收器对应的 COM 编号。若列表为空，检查设备电源、配对和驱动，然后点“刷新串口”。协议和波特率请按硬件说明设置；默认值不保证适用于所有设备。</p>
      <p>没有设备也可以进入“导入与分析”，用 CSV 或合成回放熟悉流程。合成数据仅供功能演示。</p>
      <Link to="/guide">打开完整使用手册</Link>
    </details>
    <div className="monitor-control-panel">
    <label className="monitor-title">本次记录名称（可选）
      <input maxLength={80} value={title} onChange={event => setTitle(event.target.value)}
        placeholder="留空则按日期和当天次数命名" />
    </label>
    <div className="capture-controls">
      <label>蓝牙 / USB 接收串口<select value={port} disabled={active || busy} onChange={e => setPort(e.target.value)}>
        <option value="">请选择串口</option>{ports.map(p => <option key={p.port} value={p.port}>{p.port} · {p.label}</option>)}
      </select></label>
      <details className="monitor-advanced"><summary>连接与分析设置</summary><div className="monitor-advanced-grid"><label>波特率<select value={baud} disabled={active || busy} onChange={e => setBaud(Number(e.target.value))}>
        {[9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600].map(v => <option key={v} value={v}>{v}</option>)}
      </select></label>
      <label>采集协议<select value={format} disabled={active || busy} onChange={e => setFormat(e.target.value)}>
        <option value="document_34">34 字节 · 4 组样本</option><option value="source_10">10 字节 · 1 组样本</option>
      </select></label>
      <label>分析模型<select value={model} disabled={active || busy} onChange={e => setModel(e.target.value)}>
        <option value="cnn">CNN H27 · N/S/V/F</option><option value="hgb">HGB v92 · N/S/VF</option><option value="ensemble">CNN主判 + HGB复核</option>
      </select></label>
      <Link className="monitor-model-guide" to="/guide#guide-models">不知道选哪个模型？查看使用手册 →</Link>
      </div></details>
    </div>
    <div className="actions">
      <button disabled={busy || !port || active || unsaved} onClick={() => void run(async () => {
        setSession(await post<Capture>('/acquisition/sessions', {port, baud, format, model}));
      })}>开始采集</button>
      <button className="secondary" disabled={busy || !active} onClick={() => void run(async () => {
        setSession(await post<Capture>(`/acquisition/sessions/${session!.id}/stop`));
      })}>停止采集</button>
      <button className="secondary" disabled={busy || active || !session?.sample_count || Boolean(session?.task)}
        onClick={() => void run(async () => {
          const task = await post<AnalysisTask>(`/acquisition/sessions/${session!.id}/save`, {title: title.trim()});
          navigate('/analyze?task=' + task.id);
        })}>保存并完整分析</button>
      <button className="secondary" disabled={busy || active} onClick={() => void refreshPorts()}>刷新串口</button>
      <Link className="button secondary" to="/analyze">从 CSV 分析</Link>
    </div>
    </div>
    {!ports.length && <p className="notice">未发现串口。请连接蓝牙 USB 接收器，或在 Windows 中完成蓝牙配对，然后刷新串口。</p>}
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    {session?.error && <p className="notice notice-error" role="alert">{session.error}。已收到的数据会保留，可保存后开启新会话。</p>}
    <div className="monitor-strip">
      <div><span>心率</span><strong>{session?.prediction?.heart_rate?.bpm ?? '—'}<small>次/分</small></strong></div>
      <div><span>已采集</span><strong>{session?.duration_sec.toFixed(1) ?? '0.0'}<small>秒</small></strong></div>
      <div><span>样本数</span><strong>{session?.sample_count.toLocaleString() ?? '0'}<small>500 Hz</small></strong></div>
      <div><span>已分析到</span><strong>{((session?.analysis_samples ?? 0) / 500).toFixed(1)}<small>秒</small></strong></div>
    </div>
    <div className="monitor-wave-panel">
    <div className="monitor-wave-heading"><div><h2>实时心电波形</h2><span>最近 {visibleDuration.toFixed(1)} 秒 · 可拖动调整窗口</span></div>
      <span className={`capture-status ${active ? 'is-active' : ''}`}>{active ? '数据流动中' : '等待采集'}</span></div>
    <div className="wave-toolbar"><strong>波形显示</strong>
      <div className="monitor-segmented" role="group" aria-label="波形类型">
        <button className={!raw ? 'selected' : ''} onClick={() => setRaw(false)}>滤波显示</button>
        <button className={raw ? 'selected' : ''} onClick={() => setRaw(true)}>原始信号</button>
      </div>
      <span className="hint">{raw ? '标称 mV 原始信号' : '0.5–40 Hz 因果滤波，仅用于显示'}</span>
    </div>
    <label className="monitor-window-slider">显示窗口
      <input type="range" min={1} max={5} step={0.5} value={windowSeconds}
             onChange={event => setWindowSeconds(Number(event.target.value))}
             aria-label="波形显示窗口秒数" />
      <span>{windowSeconds.toFixed(1)} 秒</span>
    </label>
    <Waveform points={visiblePoints} duration={duration} offset={start} unit="mV" />
    <div className="respiration-heading"><h2>实时呼吸波形</h2><span>ADS1292R CH1 · 原始码值</span></div>
    <Waveform channel="respiration" points={respirationPoints} duration={duration} offset={start} unit="ADC 计数" />
    </div>
    <section className="monitor-wave-panel monitor-beats" aria-labelledby="monitor-beats-title">
      <div className="monitor-wave-heading"><div><h2 id="monitor-beats-title">AI 实时心拍分类</h2>
        <span>{selectedModel === 'hgb' ? 'HGB v92' : selectedModel === 'ensemble' ? 'CNN H27 · HGB 复核' : 'CNN H27'}</span>
      </div></div>
      <div className="monitor-strip" aria-label="本次采集的累计心拍分类">
        {beatClasses.map(label => <div key={label}>
          <span className="beat-class-label">{label} · {beatNames[label]}</span>
          <strong>{beats?.by_type?.[label] ?? '—'}<small>拍</small></strong>
        </div>)}
        <div>
          <span className="beat-class-label">未分类</span>
          <strong>{beats?.unclassified_count ?? '—'}<small>拍</small></strong>
          <p className="beat-class-note">如波形不完整的心拍</p>
        </div>
      </div>
      <p className="hint monitor-wave-note" role="status">{classificationStatus}
        {active && '。模型分批更新，最近约 2.5 秒的心拍待判定。'}</p>
    </section>
  </section>;
}
