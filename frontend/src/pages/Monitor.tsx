import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnalysisTask, Prediction, WaveformPoint, post, request } from '../services/api';
import Waveform from '../components/Waveform';

interface Capture {
  id: string; status: string; error: string | null; port: string; baud: number; format: string;
  model: string; sample_count: number; duration_sec: number; received_bytes: number;
  points: (WaveformPoint & {raw: number})[]; prediction: Prediction | null;
  analysis_samples: number; analysis_pending: boolean; pending_bytes: number;
  task: AnalysisTask | null;
}
interface Port {port: string; label: string;}
const statusLabel: Record<string, string> = {running: '采集中', stopped: '已停止', error: '采集已中断',
  starting: '连接中', limit_reached: '达到记录上限'};

export default function Monitor() {
  const [ports, setPorts] = useState<Port[]>([]);
  const [port, setPort] = useState('');
  const [baud, setBaud] = useState(115200);
  const [format, setFormat] = useState('document_34');
  const [model, setModel] = useState('cnn');
  const [session, setSession] = useState<Capture | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [raw, setRaw] = useState(false);
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

  const points = (session?.points ?? []).map(p => ({t: p.t, v: raw ? p.raw : p.v}));
  const start = points[0]?.t ?? 0;
  const duration = points.length > 1 ? points[points.length - 1].t - start : 5;
  return <section className="monitor-page">
    <div className="monitor-heading"><div><p className="eyebrow">ADS1292R · 蓝牙采集</p>
      <h1>实时心电监测</h1><p>连接采集模块，在电脑上查看波形与心拍分类。</p></div>
      <span className={`capture-status ${active ? 'is-active' : ''}`} role="status">
        {connected ? session ? statusLabel[session.status] ?? session.status : '等待连接' : '服务连接中'}
      </span></div>
    <div className="capture-controls">
      <label>蓝牙 / USB 接收串口<select value={port} disabled={active || busy} onChange={e => setPort(e.target.value)}>
        <option value="">请选择串口</option>{ports.map(p => <option key={p.port} value={p.port}>{p.port} · {p.label}</option>)}
      </select></label>
      <label>波特率<select value={baud} disabled={active || busy} onChange={e => setBaud(Number(e.target.value))}>
        {[9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600].map(v => <option key={v} value={v}>{v}</option>)}
      </select></label>
      <label>采集协议<select value={format} disabled={active || busy} onChange={e => setFormat(e.target.value)}>
        <option value="document_34">34 字节 · 4 组样本</option><option value="source_10">10 字节 · 1 组样本</option>
      </select></label>
      <label>分析模型<select value={model} disabled={active || busy} onChange={e => setModel(e.target.value)}>
        <option value="cnn">CNN H27 · N/S/V/F</option><option value="hgb">HGB v92 · N/S/VF</option>
      </select></label>
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
          const task = await post<AnalysisTask>(`/acquisition/sessions/${session!.id}/save`);
          navigate('/analyze?task=' + task.id);
        })}>保存并完整分析</button>
      <button className="secondary" disabled={busy || active} onClick={() => void refreshPorts()}>刷新串口</button>
      <Link className="button secondary" to="/analyze">从 CSV 分析</Link>
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
    <div className="wave-toolbar"><strong>最近 5 秒</strong>
      <label className="inline"><input type="checkbox" checked={raw} onChange={e => setRaw(e.target.checked)} />原始波形</label>
      <span className="hint">{raw ? '标称 mV 原始信号' : '0.5–40 Hz 因果滤波，仅用于显示'}</span>
    </div>
    <Waveform points={points} duration={duration} offset={start} unit="mV" />
    <p className="hint">波形持续更新；心拍分类约每 4 秒重算本轮完整记录，在线结果至少滞后 2.5 秒，停止后再做整段分析。
      刷新或切换页面不会停止采集。最多 200000 点（约 6 分 40 秒）。</p>
    {session?.prediction?.status === 'model_unavailable' && <p className="notice notice-error">{session.prediction.explanation}</p>}
    {!session?.prediction && <p className="empty-state">采集至少 4 秒后，可查看心率预览；保存后在记录详情查看完整分类。</p>}
    <p className="hint">通道 2 为心电，通道 1 原始数据一并保存。无线帧没有序号和校验，无法证明源端无丢样；
      遇到断流或帧错误会停止，重连后请开启新会话。标称电压换算采用 2.42 V、6 倍增益。</p>
  </section>;
}
