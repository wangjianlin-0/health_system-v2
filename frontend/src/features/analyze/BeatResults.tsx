import { Prediction } from '../../services/api';

const meanings: Record<string, string> = {N: '常见心拍类', S: '室上性心拍类', V: '室性心拍类',
  F: '融合心拍类', VF: 'V/E/F 合并类', UNCLASSIFIED: '未分类'};

export default function BeatResults({prediction}: {prediction?: Prediction | null}) {
  if (!prediction?.classes) return null;
  const beats = prediction.beats;
  return <div className="beat-results">
    <div className="beat-counts">{prediction.classes.map(label => <div key={label}>
      <strong>{beats?.by_type?.[label] ?? 0}</strong><span>{label} · {meanings[label]}</span>
    </div>)}</div>
    <p className="hint">{prediction.model_version} · 电脑 CPU · 已分类 {beats?.classified_count ?? 0} 拍
      {' · '}未分类 {beats?.unclassified_count ?? 0} 拍 · {prediction.preview ? '采集中预览' : '整段分析'}
      {prediction.inference_ms != null && ` · 本轮计算 ${(prediction.inference_ms / 1000).toFixed(2)} s`}</p>
    <p className="hint">N 类不表示健康；HGB 的 VF 为 V/E/F 合并，不是心室颤动。概率用于描述模型输出，不代表诊断可信度。</p>
    {Boolean(beats?.items?.length) && <div className="beat-table" tabIndex={0} role="region" aria-label="最近100个心拍结果">
      <table><thead><tr><th>心拍</th><th>R 峰时间</th><th>类别</th><th>模型概率</th><th>结果可用时间</th></tr></thead>
        <tbody>{beats!.items!.slice(-100).map(beat => <tr key={beat.beat_id}>
          <td>#{beat.beat_id}</td><td>{beat.r_seconds.toFixed(3)} s</td>
          <td>{beat.valid ? `${beat.label} · ${meanings[beat.label] ?? ''}` : '未分类 / 边界或初始化'}</td>
          <td>{beat.confidence == null ? '—' : `${(beat.confidence * 100).toFixed(1)}%`}</td>
          <td>{((beat.decision_sample500 ?? beat.waveform_ready_sample500) / 500).toFixed(3)} s</td>
        </tr>)}</tbody></table></div>}
  </div>;
}
