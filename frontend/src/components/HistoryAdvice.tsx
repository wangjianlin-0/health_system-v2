import {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {localTimezone, request} from '../services/api';

type Advice = {
  rule_id: string;
  observation: string;
  advice: string;
  source: {title: string; section: string; url?: string};
  evidence_records: {id: string; date: string}[];
};

type PersonalReport = {
  headline: string;
  sections: {id: string; title: string; text: string; action: string; record_ids: string[]}[];
  possible_factors: {text: string; title: string; url: string}[];
  safety_notice: string | null;
  presentation: 'local' | 'qwen';
};

type HistoryAdviceResponse = {
  report: PersonalReport | null;
  qwen_available: boolean;
  measurement_count: number;
  items: Advice[];
};

export default function HistoryAdvice({refresh}: {refresh: number}) {
  const [data, setData] = useState<HistoryAdviceResponse | null>(null);
  const [error, setError] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const [polishStatus, setPolishStatus] = useState('');
  const timezone = encodeURIComponent(localTimezone());

  useEffect(() => {
    let active = true;
    setData(null);
    setError(false);
    setPolishStatus('');
    request<HistoryAdviceResponse>(`/records/advice?timezone=${timezone}`)
      .then(result => {if (active) setData(result);})
      .catch(() => {if (active) setError(true);});
    return () => {active = false;};
  }, [refresh, timezone]);

  async function polish() {
    setPolishing(true);
    try {
      const result = await request<HistoryAdviceResponse>(`/records/advice/polish?timezone=${timezone}`, {method: 'POST'});
      setData(result);
      setPolishStatus(result.report?.presentation === 'qwen' ? '已调整报告表达。' : '已显示本地报告。');
    } catch {
      setPolishStatus('暂时无法润色，仍可查看本地报告。');
    } finally {
      setPolishing(false);
    }
  }

  return <section className="panel history-advice-panel" aria-labelledby="history-advice-title">
    <div className="history-advice-heading"><div><span className="history-advice-mark" aria-hidden="true">心</span><div><h2 id="history-advice-title">个人心电观察与建议</h2><p>根据近期记录整理，供回顾与就诊沟通参考</p></div></div>
      {data && <span className="history-advice-count">近 35 天 · {data.measurement_count} 次测量</span>}
    </div>
    {error && <p role="status">暂时无法加载个人建议。</p>}
    {!error && !data && <p role="status">正在汇总个人记录…</p>}
    {data && data.measurement_count === 0 && <p>近 35 天没有个人测量记录。</p>}
    {data?.report && <div className="task-panel history-report">
      {data.report.safety_notice && <p className="notice" role="alert">{data.report.safety_notice}</p>}
      <div className="history-report-title"><span>观察摘要</span><h3>{data.report.headline}</h3></div>
      <div className="history-report-sections">{data.report.sections.map(section => <article className="history-report-section" key={section.id}>
        <h4>{section.title}</h4><p>{section.text}</p><p className="history-report-action">{section.action}</p>
        {section.record_ids.length > 0 && <details>
          <summary>查看依据记录（{section.record_ids.length}）</summary>
          <ul>{section.record_ids.map((id, index) => <li key={id}>
            <Link to={`/records/${id}`}>查看记录 {index + 1}</Link>
          </li>)}</ul>
        </details>}
      </article>)}</div>
      {data.report.possible_factors.map(factor => <div key={factor.url}>
        <h4>可能相关的情况</h4><p>{factor.text}</p><p><a href={factor.url}>{factor.title}</a></p>
      </div>)}
      {data.qwen_available && <>
        <p className="hint">点击润色会将报告的简要统计发送给通义千问。</p>
        <button className="secondary" disabled={polishing} onClick={() => void polish()}>
          {polishing ? '正在润色…' : '用通义千问润色'}
        </button>
        {polishStatus && <p role="status">{polishStatus}</p>}
      </>}
    </div>}
    {data && data.measurement_count > 0 && data.items.length > 0 && <>
      <div className="history-advice-subhead"><h3>记录中值得留意的情况</h3><span>{data.items.length} 项</span></div>
      <div className="analysis-card-grid">
        {data.items.map((item, index) => <article className="analysis-card" key={`${item.rule_id}-${index}`}>
          <span className="history-advice-index">观察 {String(index + 1).padStart(2, '0')}</span>
          <strong>{item.observation}</strong>
          <p>{item.advice}</p>
          <p className="hint history-source">依据 · {item.source.url
            ? <a href={item.source.url}>{item.source.title}</a>
            : item.source.title} · {item.source.section}</p>
          <details>
            <summary>查看相关记录（{item.evidence_records.length}）</summary>
            <ul>{item.evidence_records.map(record => <li key={record.id}>
              <Link to={`/records/${record.id}`}>{record.date} · 查看记录</Link>
            </li>)}</ul>
          </details>
        </article>)}
      </div>
    </>}
  </section>;
}
