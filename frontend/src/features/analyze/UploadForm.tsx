import { DragEvent, FormEvent, useState } from 'react';

const MAX_BYTES = 5_000_000;

export default function UploadForm({onSubmit, onReplay, busy, progress, error}: {
  onSubmit: (file: File, rate: number, model: string, title: string) => void;
  onReplay: (title: string) => void;
  busy: boolean;
  progress: number;
  error: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [rate, setRate] = useState(500);
  const [model, setModel] = useState('cnn');
  const [title, setTitle] = useState('');
  const [localError, setLocalError] = useState('');
  const [dragging, setDragging] = useState(false);

  function pick(next: File | null) {
    setLocalError('');
    if (!next) return setFile(null);
    if (!next.name.toLowerCase().endsWith('.csv')) {
      setLocalError('请选择 CSV 文件；支持单列 mV 或包含 ecg_raw 的 ADS1292R 导出文件');
      return;
    }
    if (next.size > MAX_BYTES) {
      setLocalError('CSV 最大 5 MB');
      return;
    }
    setFile(next);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setLocalError('请选择 CSV 文件');
      return;
    }
    setLocalError('');
    onSubmit(file, rate, model, title.trim());
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files?.[0] ?? null);
  }

  return <form className="upload-form" onSubmit={submit}>
    <details className="upload-format-note"><summary>支持格式与采样说明</summary>
      <p>支持单列 mV CSV、ADS1292R 原始 CSV 和本项目导出的记录 CSV。有呼吸通道时会同时导入两路波形。默认采样率为 500 Hz，请按文件的实际采样率填写。</p>
    </details>
    <div className={`dropzone${dragging ? ' dragging' : ''}`}
         onDragOver={event => {event.preventDefault(); setDragging(true);}}
         onDragLeave={() => setDragging(false)}
         onDrop={drop}>
      <input id="ecg-file" type="file" accept=".csv" onChange={event => pick(event.target.files?.[0] ?? null)} />
      <label htmlFor="ecg-file" className="dropzone-label">
        <strong>{file ? file.name : '点击选择或拖入 CSV'}</strong>
        <span>{file ? `${(file.size / 1024).toFixed(1)} KB` : 'CSV · UTF-8 · 最大 5 MB'}</span>
      </label>
    </div>
    <label className="record-title-input">记录名称（可选）
      <input maxLength={80} value={title} onChange={event => setTitle(event.target.value)}
        placeholder="留空则按日期和当天次数命名" />
    </label>
    <div className="upload-settings">
    <label>采样率 <span>Hz</span>
      <input type="number" min={50} max={2000} value={rate} required
             onChange={event => setRate(Number(event.target.value))} />
    </label>
    <label>分析模型<select value={model} onChange={event => setModel(event.target.value)}>
      <option value="cnn">CNN H27 · 四类 N/S/V/F（500 Hz）</option>
      <option value="hgb">HGB v92 · 三类 N/S/VF（500 Hz）</option>
      <option value="ensemble">CNN主判 + HGB一致性复核（500 Hz）</option>
      <option value="openecg">OpenECG · 可选依赖（500 Hz，至少 10 秒）</option>
      <option value="none">仅信号检查</option>
    </select></label>
    </div>
    <small className="hint upload-model-hint">CNN、HGB 和 OpenECG 模型对采样率及时长有要求，请按设备实际参数填写。</small>
    {progress > 0 && progress < 100 && <div className="progress" role="progressbar" aria-valuenow={progress}
          aria-valuemin={0} aria-valuemax={100}><span style={{width: `${progress}%`}} /></div>}
    {(localError || error) && <p className="notice notice-error" role="alert">{localError || error}</p>}
    <div className="actions">
      <button disabled={busy}>{busy ? '提交中…' : '导入并分析'}</button>
      <button type="button" className="secondary" disabled={busy} onClick={() => onReplay(title.trim())}>使用合成回放</button>
    </div>
  </form>;
}
