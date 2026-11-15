import { RecordDetail } from '../../services/api';

export interface PaperOptions {
  start: number;
  end: number;
  speed: number;
  gain: number;
  filtered: boolean;
}

export const PAPER_PX_PER_MM = 8;
const WIDTH = 297;
const TRACE_X = 35;
const TRACE_WIDTH = 250;
const GRID_TOP = 49;

export function paperPages(rate: number, length: number, options: PaperOptions) {
  if (!Number.isFinite(rate) || rate <= 0 || !length) throw new Error('这条记录没有可导出的波形。');
  if (![25, 50].includes(options.speed) || ![5, 10, 20].includes(options.gain)) throw new Error('走纸速度或增益无效。');
  const duration = length / rate;
  if (!Number.isFinite(options.start) || !Number.isFinite(options.end) || options.start < 0 ||
      options.end > duration + 1e-6 || options.end <= options.start) {
    throw new Error('请选择有效的导出时间范围。');
  }
  const first = Math.ceil(options.start * rate - 1e-8);
  const last = Math.min(length, Math.ceil(options.end * rate - 1e-8));
  if (last <= first) throw new Error('选定范围没有样本。');
  const rowSamples = Math.round(TRACE_WIDTH / options.speed * rate);
  return {first, last, rowSamples, count: Math.ceil((last - first) / (rowSamples * 3))};
}

export function drawEcgPaper(record: RecordDetail, options: PaperOptions, page: number): HTMLCanvasElement {
  const result = record.result;
  const samples = options.filtered ? result.waveform_processed_mV : result.waveform;
  if (result.unit !== 'mV') throw new Error('心电纸标尺要求 mV 单位，当前记录单位不符合要求。');
  if (!samples?.length) throw new Error('所选波形不可用，请切换原始波形。');
  const rate = result.sample_rate_hz;
  const pages = paperPages(rate, samples.length, options);
  if (!Number.isInteger(page) || page < 0 || page >= pages.count) throw new Error('页码无效。');
  const first = pages.first + page * pages.rowSamples * 3;
  const last = Math.min(pages.last, first + pages.rowSamples * 3);
  const rows: {first: number; last: number; center: number; height: number}[] = [];
  for (let begin = first; begin < last; begin += pages.rowSamples) {
    const end = Math.min(last, begin + pages.rowSamples);
    const values = samples.slice(begin, end);
    if (!values.every(Number.isFinite)) throw new Error('波形中有无效数值，无法导出。');
    const sorted = [...values].sort((a, b) => a - b);
    const center = sorted[Math.floor(sorted.length / 2)];
    let extent = 1;
    for (const value of values) extent = Math.max(extent, Math.abs(value - center));
    // Preserve the declared gain; grow rows for artifacts instead of normalizing or clipping.
    rows.push({first: begin, last: end, center, height: Math.max(40, Math.ceil((extent * options.gain * 2 + 14) / 5) * 5)});
  }
  const gridHeight = rows.reduce((sum, row) => sum + row.height, 0);
  const height = Math.max(210, GRID_TOP + gridHeight + 26);
  if (height > 600) throw new Error('信号幅度过大，图片高度超限。请降低增益或缩短范围后重试。');
  const canvas = document.createElement('canvas');
  canvas.width = WIDTH * PAPER_PX_PER_MM;
  canvas.height = height * PAPER_PX_PER_MM;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('浏览器不支持图片绘制。');
  ctx.scale(PAPER_PX_PER_MM, PAPER_PX_PER_MM);
  ctx.fillStyle = '#fffdfc'; ctx.fillRect(0, 0, WIDTH, height);
  const font = '"Microsoft YaHei", "Noto Sans CJK SC", sans-serif';
  function text(value: string, x: number, y: number, size = 3, color = '#242d34', bold = false) {
    ctx!.font = `${bold ? '600 ' : ''}${size}px ${font}`;
    ctx!.fillStyle = color; ctx!.fillText(value, x, y);
  }
  function short(value: string, limit: number) {
    let trimmed = value;
    while (trimmed.length && ctx!.measureText(trimmed).width > limit) trimmed = trimmed.slice(0, -1);
    return trimmed === value ? value : trimmed.slice(0, -1) + '…';
  }
  text('未卜心知', 12, 14, 6, '#1e343b', true);
  text('单导联心电记录', 49, 14, 4);
  text(`第 ${page + 1} / ${pages.count} 页`, 257, 14, 3);
  text(`记录时间  ${new Date(record.created_at).toLocaleString('zh-CN', {hour12: false})}`, 12, 24);
  ctx.font = `3px ${font}`;
  text(short('记录用户  ' + (record.owner_username || '—'), 130), 12, 30);
  text(`采样率  ${rate} Hz   ·   心率  ${result.prediction.heart_rate?.bpm ?? record.heart_rate_bpm ?? '—'} 次/分（整段）`, 12, 36);
  text(`走纸速度  ${options.speed} mm/s`, 150, 24);
  text(`增益  ${options.gain} mm/mV   ·   校准脉冲 1 mV / 200 ms`, 150, 30);
  text(`本页  ${(first / rate).toFixed(3)}–${(last / rate).toFixed(3)} s   ·   ${options.filtered ? '离线滤波波形' : '原始波形'}`, 150, 36);
  ctx.strokeStyle = '#d5c5c4'; ctx.lineWidth = .2;
  ctx.beginPath(); ctx.moveTo(12, 40); ctx.lineTo(285, 40); ctx.stroke();
  ctx.font = `2.7px ${font}`;
  text(short('单导联 · ' + (result.lead || record.lead || '未命名导联'), 130), 12, 45, 2.7);
  text(`每行 ${TRACE_WIDTH / options.speed} s · 每行减中位值居中 · 未做幅度归一化`, 150, 45, 2.7);
  ctx.fillStyle = '#fff7f6'; ctx.fillRect(12, GRID_TOP, 273, gridHeight);
  for (let x = 12; x <= 285; x++) {
    ctx.strokeStyle = (x - TRACE_X) % 5 === 0 ? '#e3a3a3' : '#f2d3d0';
    ctx.lineWidth = (x - TRACE_X) % 5 === 0 ? .16 : .08;
    ctx.beginPath(); ctx.moveTo(x, GRID_TOP); ctx.lineTo(x, GRID_TOP + gridHeight); ctx.stroke();
  }
  for (let y = GRID_TOP; y <= GRID_TOP + gridHeight; y++) {
    ctx.strokeStyle = (y - GRID_TOP) % 5 === 0 ? '#e3a3a3' : '#f2d3d0';
    ctx.lineWidth = (y - GRID_TOP) % 5 === 0 ? .16 : .08;
    ctx.beginPath(); ctx.moveTo(12, y); ctx.lineTo(285, y); ctx.stroke();
  }
  let rowTop = GRID_TOP;
  for (const row of rows) {
    const baseline = rowTop + row.height / 2;
    text(`${(row.first / rate).toFixed(2)} s`, 13, rowTop + 4, 2.5);
    text(`基线 ${row.center.toFixed(3)} mV`, 230, rowTop + 4, 2.5, '#6e5555');
    ctx.strokeStyle = '#222b30'; ctx.lineWidth = .22;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(15, baseline); ctx.lineTo(17, baseline); ctx.lineTo(17, baseline - options.gain);
    ctx.lineTo(17 + options.speed * .2, baseline - options.gain);
    ctx.lineTo(17 + options.speed * .2, baseline); ctx.lineTo(20 + options.speed * .2, baseline);
    ctx.stroke();
    ctx.beginPath();
    for (let index = row.first; index < row.last; index++) {
      const x = TRACE_X + (index - row.first) / rate * options.speed;
      const y = baseline - (samples[index] - row.center) * options.gain;
      if (index === row.first) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    for (let second = 0; second <= TRACE_WIDTH / options.speed; second++) {
      if (row.first + second * rate > row.last) break;
      const x = TRACE_X + second * options.speed;
      text(`${(row.first / rate + second).toFixed(1)}`, x - 1.5, rowTop + row.height - 1.8, 2.3, '#785b5b');
    }
    rowTop += row.height;
  }
  text(`记录编号  ${record.id}`, 12, rowTop + 8, 2.7);
  text(`图像 ${canvas.width} × ${canvas.height} px · 8 px/mm · 原尺寸宽 297 mm`, 150, rowTop + 8, 2.7);
  ctx.font = `2.7px ${font}`;
  text(short(`模型  ${record.model_version || '未加载'}   ·   ${result.prediction.label || '未产生分类结果'}`, 272), 12, rowTop + 14, 2.7);
  text('单导联辅助记录，分析结果供复核参考。打印请保持原尺寸，勿使用“适合页面”缩放。', 12, rowTop + 20, 2.7, '#6e5555');
  return canvas;
}

// Override Canvas's default 96 dpi so the PNG's original print size preserves the physical grid.
export async function paperPng(canvas: HTMLCanvasElement): Promise<Blob> {
  const png = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
    blob => blob ? resolve(blob) : reject(new Error('PNG 生成失败，请重试。')), 'image/png'));
  const bytes = new Uint8Array(await png.arrayBuffer());
  const chunk = new Uint8Array(21);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, 9);
  chunk.set([112, 72, 89, 115], 4);
  view.setUint32(8, PAPER_PX_PER_MM * 1000);
  view.setUint32(12, PAPER_PX_PER_MM * 1000);
  chunk[16] = 1;
  let crc = 0xffffffff;
  for (const byte of chunk.slice(4, 17)) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  view.setUint32(17, (crc ^ 0xffffffff) >>> 0);
  const parts: BlobPart[] = [bytes.slice(0, 33), chunk];
  let offset = 33;
  while (offset < bytes.length) {
    const length = new DataView(bytes.buffer, bytes.byteOffset + offset, 4).getUint32(0);
    const type = String.fromCharCode(...bytes.slice(offset + 4, offset + 8));
    if (type !== 'pHYs') parts.push(bytes.slice(offset, offset + length + 12));
    offset += length + 12;
  }
  return new Blob(parts, {type: 'image/png'});
}
