import { DragEvent, FormEvent, useState } from 'react';

const MAX_BYTES = 2_000_000;

export default function UploadForm({onSubmit, onReplay, busy, progress, error}: {
  onSubmit: (file: File, rate: number) => void;
  onReplay: () => void;
  busy: boolean;
  progress: number;
  error: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [rate, setRate] = useState(500);
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
      setLocalError('CSV 最大 2 MB');
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
    onSubmit(file, rate);
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files?.[0] ?? null);
  }

  return <form onSubmit={submit}>
    <p>支持单列 mV CSV（value/sample/mv 表头），或包含 ecg_raw 的 ADS1292R 原始 CSV，系统按 2.42 V、6 倍增益换算。默认采样率为 500 Hz；其他设备请按实际采样率修改。</p>
    <div className={`dropzone${dragging ? ' dragging' : ''}`}
         onDragOver={event => {event.preventDefault(); setDragging(true);}}
         onDragLeave={() => setDragging(false)}
         onDrop={drop}>
      <input id="ecg-file" type="file" accept=".csv" onChange={event => pick(event.target.files?.[0] ?? null)} />
      <label htmlFor="ecg-file" className="dropzone-label">
        <strong>{file ? file.name : '点击选择或拖入 CSV'}</strong>
        <span>{file ? `${(file.size / 1024).toFixed(1)} KB` : 'mV 或 ADS1292R 原始 CSV · UTF-8 · ≤2 MB'}</span>
      </label>
    </div>
    <label>采样率 Hz
      <input type="number" min={50} max={2000} value={rate} required
             onChange={event => setRate(Number(event.target.value))} />
    </label>
    <small className="hint">示例：仓库 csv/ptbxl_00001_lead_II_500Hz_10s.csv 为 500 Hz、10 秒。</small>
    {progress > 0 && progress < 100 && <div className="progress" role="progressbar" aria-valuenow={progress}
          aria-valuemin={0} aria-valuemax={100}><span style={{width: `${progress}%`}} /></div>}
    {(localError || error) && <p className="notice notice-error" role="alert">{localError || error}</p>}
    <div className="actions">
      <button disabled={busy}>{busy ? '提交中…' : '导入并分析'}</button>
      <button type="button" className="secondary" disabled={busy} onClick={onReplay}>使用合成回放</button>
    </div>
  </form>;
}
