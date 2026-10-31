import { WaveformPoint } from '../services/api';

export function decimate(values: number[], buckets: number): number[] {
  if (values.length <= buckets * 2) return values;
  const size = Math.ceil(values.length / buckets);
  const output: number[] = [];
  for (let start = 0; start < values.length; start += size) {
    const end = Math.min(values.length, start + size);
    let minIndex = start;
    let maxIndex = start;
    for (let index = start + 1; index < end; index += 1) {
      if (values[index] < values[minIndex]) minIndex = index;
      if (values[index] > values[maxIndex]) maxIndex = index;
    }
    if (minIndex <= maxIndex) {
      output.push(values[minIndex], values[maxIndex]);
    } else {
      output.push(values[maxIndex], values[minIndex]);
    }
  }
  return output;
}

export default function Waveform({values = [], points, duration, unit, offset = 0}: {
  values?: number[];
  points?: WaveformPoint[];
  duration: number;
  unit: string;
  offset?: number;
}) {
  const fromWindow = Boolean(points && points.length);
  if (!fromWindow && !values.length) return <p className="empty-state">没有波形数据。</p>;

  const source = fromWindow ? points! : decimate(values, 600).map((value, index, array) => ({
    t: offset + (index / Math.max(array.length - 1, 1)) * duration,
    v: value,
  }));
  if (!source.length) return <p className="empty-state">没有波形数据。</p>;

  let min = Infinity;
  let max = -Infinity;
  for (const point of source) {
    if (point.v < min) min = point.v;
    if (point.v > max) max = point.v;
  }
  const span = max - min || 1;
  const left = 44;
  const right = 964;
  const top = 26;
  const bottom = 198;
  const safeDuration = Math.max(duration, 1e-9);
  const xOf = (time: number) => {
    const ratio = Math.min(1, Math.max(0, (time - offset) / safeDuration));
    return left + ratio * (right - left);
  };
  const coordinates = source.map(point => {
    const y = bottom - ((point.v - min) / span) * (bottom - top);
    return `${xOf(point.t).toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const startLabel = offset === 0 ? '0 s' : `${offset.toFixed(2)} s`;
  const endLabel = `${(offset + duration).toFixed(2)} s`;

  return <figure>
    <svg viewBox="0 0 1000 240" role="img"
         aria-label={`心电波形，${offset.toFixed(2)} 到 ${(offset + duration).toFixed(2)} 秒，${source.length} 个绘制点`}>
      <defs>
        <pattern id="ecg-grid" width="50" height="40" patternUnits="userSpaceOnUse">
          <path d="M 50 0 L 0 0 0 40" fill="none" stroke="#dce8e3" />
        </pattern>
      </defs>
      <rect width="1000" height="240" fill="url(#ecg-grid)" />
      <line x1={left} y1={top} x2={left} y2={bottom} stroke="#b9cfca" />
      <line x1={left} y1={bottom} x2={right} y2={bottom} stroke="#b9cfca" />
      <polyline points={coordinates} fill="none" stroke="#157a70" strokeWidth="1.3" />
      <text x={left - 6} y={top + 4} textAnchor="end" className="wave-label">{max.toFixed(3)}</text>
      <text x={left - 6} y={bottom} textAnchor="end" className="wave-label">{min.toFixed(3)}</text>
      <text x={left} y={224} textAnchor="start" className="wave-label">{startLabel}</text>
      <text x={right} y={224} textAnchor="end" className="wave-label">{endLabel}</text>
    </svg>
    <figcaption>
      窗口 {startLabel}–{endLabel} · 幅值 {min.toFixed(3)}–{max.toFixed(3)} {unit}
      {fromWindow ? ' · 服务端按窗口返回包络极值' : ' · 按像素桶保留极值，避免漏掉尖峰'}
    </figcaption>
  </figure>;
}
