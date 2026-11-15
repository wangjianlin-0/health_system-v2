import { useEffect, useRef, useState } from 'react';
import { RecordDetail } from '../../services/api';
import { drawEcgPaper, paperPages, paperPng, PaperOptions } from './ecgPaper';

export default function EcgImageExport({record, start, end, onClose}: {
  record: RecordDetail; start: number; end: number; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [options, setOptions] = useState<PaperOptions>({start, end, speed: 25, gain: 10, filtered: false});
  const [page, setPage] = useState(0);
  const [pages, setPages] = useState(1);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [rendering, setRendering] = useState(true);
  const duration = record.result.waveform.length / record.result.sample_rate_hz;

  useEffect(() => {
    const element = dialog.current;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    element?.showModal();
    return () => {document.body.style.overflow = previous; element?.close();};
  }, []);

  useEffect(() => {
    let active = true;
    let url = '';
    canvas.current = null;
    setRendering(true); setError(''); setPreview('');
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          await document.fonts.ready;
          const source = options.filtered ? record.result.waveform_processed_mV : record.result.waveform;
          const count = paperPages(record.result.sample_rate_hz, source?.length ?? 0, options).count;
          if (!active) return;
          setPages(count);
          const next = drawEcgPaper(record, options, Math.min(page, count - 1));
          const blob = await paperPng(next);
          if (active) {canvas.current = next; url = URL.createObjectURL(blob); setPreview(url);}
        } catch (caught) {if (active) setError((caught as Error).message);}
        finally {if (active) setRendering(false);}
      })();
    }, 180);
    return () => {active = false; window.clearTimeout(timer); if (url) URL.revokeObjectURL(url);};
  }, [record, options, page]);

  function update(next: Partial<PaperOptions>) {
    canvas.current = null; setRendering(true); setPreview('');
    setPage(0); setOptions(current => ({...current, ...next}));
  }
  async function download() {
    if (!canvas.current) return;
    setBusy(true); setError('');
    try {
      const blob = await paperPng(canvas.current);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `ecg-${record.id}-page-${page + 1}.png`;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) {setError((caught as Error).message);}
    finally {setBusy(false);}
  }

  return <dialog className="ecg-export-dialog" ref={dialog} aria-labelledby="ecg-export-title" onCancel={onClose}>
    <div className="ecg-export-head"><div><h2 id="ecg-export-title">导出心电图片</h2>
      <p>红色方格心电纸 · 单导联连续分行 · 高清 PNG</p></div>
      <button className="secondary" onClick={onClose} aria-label="关闭心电图片导出">关闭</button></div>
    <div className="ecg-export-controls">
      <label>开始时间（秒）<input type="number" min={0} max={duration} step={0.1} value={options.start}
        onChange={event => update({start: Number(event.target.value)})} /></label>
      <label>结束时间（秒）<input type="number" min={0} max={duration} step={0.1} value={options.end}
        onChange={event => update({end: Number(event.target.value)})} /></label>
      <label>走纸速度<select value={options.speed} onChange={event => update({speed: Number(event.target.value)})}>
        <option value={25}>25 mm/s</option><option value={50}>50 mm/s</option></select></label>
      <label>增益<select value={options.gain} onChange={event => update({gain: Number(event.target.value)})}>
        <option value={5}>5 mm/mV</option><option value={10}>10 mm/mV</option><option value={20}>20 mm/mV</option></select></label>
      <label>波形<select value={options.filtered ? 'filtered' : 'raw'} onChange={event => update({filtered: event.target.value === 'filtered'})}>
        <option value="raw">原始 mV</option>
        {record.result.waveform_processed_mV?.length === record.result.waveform.length && <option value="filtered">离线节律滤波</option>}
      </select></label>
    </div>
    <div className="ecg-export-tools"><button className="secondary" onClick={() => update({start: 0, end: duration})}>选择完整记录</button>
      <span>每页 3 行，每行 {250 / options.speed} 秒；长记录分为 {pages} 页。</span></div>
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <div className="ecg-export-preview" aria-busy={rendering}>
      {rendering && <p role="status">正在生成心电纸…</p>}
      {preview && <img src={preview} alt={`单导联心电纸预览，第 ${page + 1} 页，${options.speed}毫米每秒，${options.gain}毫米每毫伏`} />}
    </div>
    <p className="hint">1 mm 小格、5 mm 大格；每行减去中位值以居中，保留原幅值变化并标注基线。
      原尺寸宽 297 mm，打印请使用原尺寸。图片按所选时间范围绘制完整样本。</p>
    <div className="ecg-export-footer"><div className="actions">
      <button className="secondary" disabled={page <= 0 || rendering} onClick={() => setPage(p => p - 1)}>上一页</button>
      <span className="hint">第 {page + 1} / {pages} 页</span>
      <button className="secondary" disabled={page >= pages - 1 || rendering} onClick={() => setPage(p => p + 1)}>下一页</button></div>
      <button disabled={busy || rendering || !preview || Boolean(error)} onClick={() => void download()}>
        {busy ? '正在导出…' : `下载第 ${page + 1} 页 PNG`}</button></div>
  </dialog>;
}
