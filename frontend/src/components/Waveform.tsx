import { useId } from 'react';
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

export default function Waveform({values = [], points, duration, unit, offset = 0, markers = [], beatInterval}: {
  values?: number[];
  points?: WaveformPoint[];
  duration: number;
  unit: string;
  offset?: number;
  markers?: {time_sec: number; label: string; kind?: 'normal' | 'attention' | 'selected'}[];
  beatInterval?: {start: number; end: number};
}) {
  const gridId = useId();
  const fromWindow = Boolean(points && points.length);
  if (!fromWindow && !values.length) return <p className="empty-state">没有波形数据。</p>;

  const source: WaveformPoint[] = fromWindow ? points! : [];
  if (!fromWindow) {
    const size = Math.max(1, Math.ceil(values.length / 600));
    for (let start = 0; start < values.length; start += size) {
      const end = Math.min(values.length, start + size);
      let minIndex = start, maxIndex = start;
      for (let index = start + 1; index < end; index++) {
        if (values[index] < values[minIndex]) minIndex = index;
        if (values[index] > values[maxIndex]) maxIndex = index;
      }
      for (const index of [...new Set([minIndex, maxIndex])].sort((a, b) => a - b)) {
        source.push({t: offset + index / Math.max(values.length - 1, 1) * duration, v: values[index]});
      }
    }
  }
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
         aria-label={`心电波形，${offset.toFixed(2)} 到 ${(offset + duration).toFixed(2)} 秒，${source.length} 个绘制点${beatInterval ? `，选中 RR 间期 ${Math.round((beatInterval.end - beatInterval.start) * 1000)} 毫秒` : ''}`}>
      <defs>
        <pattern id={gridId} width="50" height="40" patternUnits="userSpaceOnUse">
          <path d="M 50 0 L 0 0 0 40" fill="none" stroke="#dce8e3" />
        </pattern>
      </defs>
      <rect width="1000" height="240" fill={`url(#${gridId})`} />
      <line x1={left} y1={top} x2={left} y2={bottom} stroke="#b9cfca" />
      <line x1={left} y1={bottom} x2={right} y2={bottom} stroke="#b9cfca" />
      {beatInterval && <g aria-hidden="true" className="wave-rr-bracket">
        <rect x={xOf(beatInterval.start)} y={top} width={xOf(beatInterval.end) - xOf(beatInterval.start)}
              height={bottom - top} fill="#127c7212" />
        <path d={`M ${xOf(beatInterval.start)} 36 V 28 H ${xOf(beatInterval.end)} V 36`}
              stroke="#17766d" strokeWidth="1.8" fill="none" />
      </g>}
      {markers.filter(marker => marker.time_sec >= offset - 1e-8 && marker.time_sec <= offset + duration + 1e-8).map((marker, index) => {
        const markerX = xOf(marker.time_sec);
        const attention = marker.kind === 'attention';
        if (marker.kind === 'selected') return <g key={`${marker.time_sec}-${index}`} className="wave-rr-marker" aria-hidden="true">
          <line x1={markerX} x2={markerX} y1={top} y2={bottom} stroke="#17766d" strokeDasharray="4 4" />
          <circle cx={markerX} cy={bottom} r="4" fill="#17766d" />
          <text x={markerX} y={top - 6} textAnchor="middle" fill="#155f58" fontSize="13" fontWeight="600">{marker.label}</text>
        </g>;
        return <g key={`${marker.time_sec}-${index}`}>
          {attention && <rect x={markerX - 9} y={top} width="18" height={bottom - top}
                              fill="#df46531a" />}
          <circle cx={markerX} cy={top + 8} r={attention ? 3.5 : 2.4}
                  fill={attention ? '#d43e50' : '#77859a'} />
          <text x={markerX} y={top - 3} textAnchor="middle"
                className={attention ? 'wave-beat-label is-attention' : 'wave-beat-label'}>{marker.label}</text>
        </g>;
      })}
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
