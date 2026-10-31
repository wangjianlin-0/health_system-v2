import { RecordTrendPoint } from '../services/api';

export default function TrendChart({days}: {days: RecordTrendPoint[]}) {
  const total = days.reduce((sum, point) => sum + point.records, 0);
  if (!days.length) return <p className="empty-state">暂无趋势数据。导入第一条记录后会在这里显示每日记录数与平均心率。</p>;

  const width = 760;
  const height = 200;
  const padding = {top: 16, right: 18, bottom: 30, left: 38};
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const maxRecords = Math.max(1, ...days.map(point => point.records));
  const rates = days.map(point => point.heart_rate_bpm).filter((value): value is number => value != null);
  const maxRate = Math.max(100, ...rates);
  const minRate = Math.min(40, ...rates);
  const slot = plotWidth / days.length;
  const barWidth = Math.max(2, Math.min(18, slot * 0.55));
  const x = (index: number) => padding.left + slot * index + slot / 2;
  const yRecords = (value: number) => padding.top + plotHeight - (value / maxRecords) * plotHeight;
  const yRate = (value: number) => padding.top + plotHeight - ((value - minRate) / (maxRate - minRate || 1)) * plotHeight;

  const linePoints = days
    .map((point, index) => point.heart_rate_bpm == null ? null : `${x(index)},${yRate(point.heart_rate_bpm)}`)
    .filter((value): value is string => value != null)
    .join(' ');

  const labelEvery = Math.max(1, Math.ceil(days.length / 8));

  return <figure className="trend-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img"
         aria-label={`近 ${days.length} 天趋势：共 ${total} 条记录，心率折线`}>
      <pattern id="trend-grid" width="38" height="38" patternUnits="userSpaceOnUse">
        <path d="M 38 0 L 0 0 0 38" fill="none" stroke="#e3ece9" />
      </pattern>
      <rect x={padding.left} y={padding.top} width={plotWidth} height={plotHeight} fill="url(#trend-grid)" />
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
      {days.map((point, index) => point.heart_rate_bpm == null ? null :
        <circle key={`dot-${point.date}`} className="trend-dot" cx={x(index)} cy={yRate(point.heart_rate_bpm)} r="2.5" />)}
      <text x={padding.left - 6} y={padding.top + 4} textAnchor="end" className="trend-label">{maxRecords}</text>
      <text x={padding.left - 6} y={padding.top + plotHeight} textAnchor="end" className="trend-label">0</text>
    </svg>
    <figcaption>柱：每日记录数（最高 {maxRecords} 条）· 线：已有心率的日均值 · 时区由浏览器提供</figcaption>
  </figure>;
}
