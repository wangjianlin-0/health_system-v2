import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RecordTrendPoint } from '../services/api';

export default function TrendChart({days}: {days: RecordTrendPoint[]}) {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const total = days.reduce((sum, point) => sum + point.records, 0);
  if (!days.length) return <p className="empty-state">暂无趋势数据。导入第一条记录后会在这里显示每日记录数与平均心率。</p>;

  const width = 760;
  const height = 200;
  const padding = {top: 16, right: 18, bottom: 30, left: 38};
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxRecords = Math.max(1, ...days.map(point => point.records));
  const rates = days.map(point => point.heart_rate_bpm).filter((value): value is number => value != null);
  const maxRate = Math.max(110, ...rates);
  const minRate = 50;
  const slot = plotWidth / days.length;
  const barWidth = Math.max(2, Math.min(18, slot * 0.55));
  const x = (index: number) => padding.left + slot * index + slot / 2;
  const yRecords = (value: number) => padding.top + plotHeight - (value / maxRecords) * plotHeight;
  const yRate = (value: number) => padding.top + plotHeight - ((value - minRate) / (maxRate - minRate || 1)) * plotHeight;
  const baseline = rates.length ? rates.reduce((sum, rate) => sum + rate, 0) / rates.length : null;
  const selectedPoint = days.find(point => point.date === selectedDate) ?? null;
  const yTicks = [50, 60, 70, 80, 90, 100, 110];

  const linePoints = days
    .map((point, index) => point.heart_rate_bpm == null ? null : `${x(index)},${yRate(point.heart_rate_bpm)}`)
    .filter((value): value is string => value != null)
    .join(' ');

  const labelEvery = Math.max(1, Math.ceil(days.length / 8));

  return <figure className="trend-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img"
         aria-label={`近 ${days.length} 天趋势：共 ${total} 条记录，心率折线`}>
      <rect x={padding.left} y={yRate(100)} width={plotWidth} height={yRate(60) - yRate(100)} className="trend-normal-band" />
      {yTicks.map(tick => <g key={tick}>
        <line x1={padding.left} x2={width - padding.right} y1={yRate(tick)} y2={yRate(tick)}
              className={tick === 60 || tick === 100 ? 'trend-threshold' : 'trend-grid-line'} />
        <text x={padding.left - 7} y={yRate(tick) + 3} textAnchor="end"
              className={tick === 60 || tick === 100 ? 'trend-label trend-threshold-label' : 'trend-label'}>{tick}</text>
      </g>)}
      {baseline != null && <line x1={padding.left} x2={width-padding.right} y1={yRate(baseline)} y2={yRate(baseline)} className="trend-baseline" />}
      {days.map((point, index) => {
        const barHeight = (point.records / maxRecords) * plotHeight;
        const hint = point.heart_rate_bpm == null
          ? `${point.date}：${point.records} 条，暂无心率`
          : `${point.date}：${point.records} 条，平均心率 ${point.heart_rate_bpm}`;
        return <g key={point.date}>
          <title>{hint}</title>
          <rect className="trend-bar" x={x(index) - barWidth / 2} y={yRecords(point.records)}
                width={barWidth} height={Math.max(point.records ? 2 : 0, barHeight)} rx="2" />
          {index % labelEvery === 0 && <text x={x(index)} y={height - 10} textAnchor="middle"
                className="trend-label">{point.date.slice(5)}</text>}
        </g>;
      })}
      {linePoints && <polyline className="trend-line" points={linePoints} fill="none" />}
      {days.map((point, index) => point.heart_rate_bpm == null ? null : <g key={`dot-${point.date}`}>
        <circle className={point.heart_rate_bpm < 60 || point.heart_rate_bpm > 100 ? 'trend-dot is-watch' : 'trend-dot'}
                cx={x(index)} cy={yRate(point.heart_rate_bpm)} r="4" />
        <circle className="trend-hit-area" cx={x(index)} cy={yRate(point.heart_rate_bpm)} r="10"
                role="button" tabIndex={0} aria-label={`${point.date} 心率 ${point.heart_rate_bpm} 次/分`}
                onClick={() => setSelectedDate(selectedDate === point.date ? null : point.date)}
                onKeyDown={event => {if (event.key === 'Enter' || event.key === ' ') setSelectedDate(selectedDate === point.date ? null : point.date);}} />
        <text x={x(index)} y={yRate(point.heart_rate_bpm)-10} textAnchor="middle" className="trend-point-label">{point.heart_rate_bpm}</text>
      </g>)}
      <line x1={padding.left} x2={width-padding.right} y1={padding.top+plotHeight} y2={padding.top+plotHeight} className="trend-axis" />
    </svg>
    {selectedPoint && <div className="trend-selected" role="status">
      <div><span>{new Date(selectedPoint.date + 'T12:00:00').toLocaleDateString()}</span><span>{selectedPoint.records} 条记录</span></div>
      <strong>{selectedPoint.heart_rate_bpm} <small>BPM</small></strong>
      <p>当日平均心率 · 范围 {selectedPoint.heart_rate_min_bpm ?? '—'}–{selectedPoint.heart_rate_max_bpm ?? '—'} BPM</p>
      <Link to={`/records?range=all&from=${selectedPoint.date}&to=${selectedPoint.date}`}>查看当日记录 →</Link>
    </div>}
    <figcaption>柱：每日记录数 · 线：当日平均心率 · 虚线：所选周期的平均值</figcaption>
  </figure>;
}
