import { FormEvent, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Waveform from '../components/Waveform';
import { localTimezone, post, qualityLabel, recordSourceLabel, request } from '../services/api';
import type { WaveformWindow } from '../services/api';
import './familyCare.css';

type CareRecord = {
  id: string; title?: string; created_at: string; source: string | null;
  duration_sec?: number; sample_rate_hz?: number; heart_rate_bpm?: number;
  quality_status: string | null; quality_score?: number; rr_mean_ms?: number;
  r_peak_count?: number; review_level?: string;
};
type Entry = {id: string; mine: number; sender_name: string; created_at: string};
type CareData = {
  owner_name: string; relative_name: string; is_owner: boolean; callback_phone: string | null;
  records: CareRecord[]; record_count: number; week: {date: string; count: number}[];
  items: {id: string; title: string; due_time: string; done: number}[];
  messages: (Entry & {text: string; read_at: string | null})[];
  contacts: {id: string; name: string; relation: string; phone: string; preferred: number}[];
  drills: (Entry & {acknowledged_at: string | null})[];
};
const tabs = [
  ['overview', '健康概览与门诊便签'], ['wave', '心电波形速览'],
  ['care', '照护清单与留言'], ['alerts', '提醒台账与联系人'],
] as const;

function today() {
  const local = new Date();
  return `${local.getFullYear()}-${String(local.getMonth() + 1).padStart(2, '0')}-${String(local.getDate()).padStart(2, '0')}`;
}

function dateText(value: string) {
  return new Date(value).toLocaleString('zh-CN', {hour12: false});
}

function recordTitle(record: CareRecord) {
  return record.title || `心电记录 · ${dateText(record.created_at)}`;
}

export default function FamilyCare() {
  const {id} = useParams();
  return id ? <CareWorkspace key={id} id={id} /> : null;
}

function CareWorkspace({id}: {id: string}) {
  const [data, setData] = useState<CareData | null>(null);
  const [tab, setTab] = useState<(typeof tabs)[number][0]>('overview');
  const [selectedId, setSelectedId] = useState('');
  const [wave, setWave] = useState<WaveformWindow | null>(null);
  const [waveError, setWaveError] = useState('');
  const [readError, setReadError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [itemTitle, setItemTitle] = useState('');
  const [itemTime, setItemTime] = useState('08:00');
  const [note, setNote] = useState('');
  const endpoint = `/family/care/${id}`;
  const selected = data?.records.find(record => record.id === selectedId) ?? data?.records[0];

  useEffect(() => {
    let active = true;
    let timer: number;
    async function refresh() {
      try {
        const next = await request<CareData>(`${endpoint}?day=${today()}&timezone=${encodeURIComponent(localTimezone())}`);
        if (active) {setData(next); setReadError('');}
      } catch (caught) {
        if (active) {setData(null); setReadError((caught as Error).message);}
      } finally {
        if (active) timer = window.setTimeout(() => void refresh(), 10000);
      }
    }
    void refresh();
    return () => {active = false; window.clearTimeout(timer);};
  }, [endpoint, reload]);

  const waveId = tab === 'wave' ? selected?.id : undefined;
  useEffect(() => {
    setWave(null);
    setWaveError('');
    if (!waveId) return;
    let active = true;
    request<WaveformWindow>(`/records/${waveId}/waveform?start_sec=0&end_sec=10&max_points=900`)
      .then(value => {if (active) setWave(value);})
      .catch(error => {if (active) setWaveError(error.message);});
    return () => {active = false;};
  }, [waveId]);

  async function act(operation: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage('');
    try {
      await operation();
      setMessage(success);
      setReload(value => value + 1);
    } catch (caught) {
      setMessage((caught as Error).message);
      setReload(value => value + 1);
    } finally {setBusy(false);}
  }

  function submitContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    void act(async () => {
      await post(endpoint + '/contacts', Object.fromEntries(fields));
      form.reset();
    }, '已保存联系人');
  }

  const latest = data?.records[0];
  const summary = data && latest ? [
    `姓名：${data.owner_name}`, `测量时间：${dateText(latest.created_at)}`,
    `记录：${recordTitle(latest)}`, `估算心率：${latest.heart_rate_bpm == null ? '未获得' : latest.heart_rate_bpm + ' 次/分'}`,
    `信号质量：${qualityLabel(latest.quality_status)}`, '可携带原始心电波形和测量时的感受，与医生沟通。',
  ].join('\n') : null;

  return <section className="care-workspace">
    <Link className="care-back" to="/family">← 返回家庭协同</Link>
    <header className="care-heading">
      <div><h1>亲属关怀视窗</h1>
        {data && <p>{data.owner_name} · {data.is_owner ? `与 ${data.relative_name} 协作` : '已授权共享'}</p>}
      </div>
      {data && !data.is_owner && data.callback_phone &&
        <a className="button" href={`tel:${data.callback_phone}`}>呼叫 {data.owner_name}</a>}
    </header>
    {readError && <p className="notice" role="alert">{readError}</p>}
    {!data && !readError && <p role="status">正在加载亲属关怀…</p>}
    {data && <>
      <div className="care-tabs" role="group" aria-label="关怀功能">
        {tabs.map(([key, label]) => <button key={key} type="button" aria-pressed={tab === key}
          className={tab === key ? 'selected' : ''} onClick={() => {setTab(key); setMessage('');}}>{label}</button>)}
      </div>
      {message && <p className="care-feedback" role="status">{message}</p>}
      {tab === 'overview' && <div className="care-grid">
        <article className="care-card"><h2>最近一次心电记录</h2>
          {latest ? <>
            <p className="care-muted">{dateText(latest.created_at)} · {recordSourceLabel(latest.source)}</p>
            <div className="care-reading"><strong>{latest.heart_rate_bpm ?? '—'}</strong><span>次/分 · 估算心率</span></div>
            <p>{qualityLabel(latest.quality_status)}{latest.quality_score != null && ` · 质量 ${latest.quality_score} / 100`}</p>
            <div className="care-actions"><button onClick={() => {setSelectedId(latest.id); setTab('wave');}}>查看波形</button>
              <Link to={`/records/${latest.id}`}>完整记录 →</Link></div>
          </> : <p>对方还没有可查看的心电记录。</p>}
          <h3>近 7 天测量记录</h3>
          <ul className="care-week">{data.week.map(day => <li key={day.date}><span>{day.date.slice(5).replace('-', '/')}</span><strong>{day.count}</strong></li>)}</ul>
        </article>
        <article className="care-card"><h2>门诊沟通便签</h2>
          <p className="care-muted">根据最近一条共享记录整理，便于陪诊时出示。</p>
          {summary ? <>
            <pre className="care-summary">{summary}</pre>
            <button className="secondary" onClick={async () => {
              try {await navigator.clipboard.writeText(summary); setMessage('已复制门诊便签');}
              catch {setMessage('浏览器未允许复制，可选中便签文字手动复制。');}
            }}>复制门诊便签</button>
          </> : <p>有共享记录后可生成便签。</p>}
        </article>
      </div>}
      {tab === 'wave' && <div className="care-grid care-wave-grid">
        <article className="care-card"><h2>心电记录</h2><p className="care-muted">共 {data.record_count} 条，显示最近 {data.records.length} 条。</p>
          <div className="care-record-list">{data.records.map(record => <button type="button" key={record.id}
            aria-pressed={selected?.id === record.id} onClick={() => setSelectedId(record.id)}>
            <strong>{recordTitle(record)}</strong>
            <small>{dateText(record.created_at)} · {record.heart_rate_bpm ?? '—'} 次/分</small>
          </button>)}</div>
        </article>
        <article className="care-card"><h2>心电波形速览</h2>
          {selected ? <>
            <p>{recordTitle(selected)} · {selected.sample_rate_hz ?? '—'} Hz</p>
            <Link className="button secondary" to={`/records/${selected.id}`}>查看完整分析</Link>
            {waveError && <p className="notice" role="alert">{waveError}</p>}
            {wave?.record_id === selected.id ? <Waveform
              points={wave.points} duration={wave.end_sec - wave.start_sec} offset={wave.start_sec} unit={wave.unit}
            /> : !waveError && <p role="status">正在加载记录波形…</p>}
            <dl className="care-metrics">
              <div><dt>平均 RR</dt><dd>{selected.rr_mean_ms == null ? '—' : selected.rr_mean_ms + ' ms'}</dd></div>
              <div><dt>质量评分</dt><dd>{selected.quality_score ?? '—'}</dd></div>
              <div><dt>检测 R 峰</dt><dd>{selected.r_peak_count ?? '—'}</dd></div>
            </dl>
          </> : <p>暂无共享波形。</p>}
        </article>
      </div>}
      {tab === 'care' && <div className="care-grid">
        <article className="care-card"><h2>今日照护清单</h2>
          <p className="care-muted">已完成 {data.items.filter(item => item.done).length} / {data.items.length} 项</p>
          <ul className="care-list">{data.items.map(item => <li key={item.id}>
            <label className="care-check"><input type="checkbox" checked={Boolean(item.done)} disabled={busy}
              onChange={event => {const done = event.target.checked; void act(
                () => request(endpoint + '/items/' + item.id, {method: 'PATCH', body: JSON.stringify({done})}), '进度已保存');}} />
              <span><b>{item.due_time}</b> {item.title}</span></label>
          </li>)}</ul>
          <form className="care-form" onSubmit={event => {event.preventDefault(); void act(async () => {
            await post(endpoint + '/items', {title: itemTitle, due_date: today(), due_time: itemTime});
            setItemTitle('');
          }, '已添加到今日清单');}}>
            <label>时间<input type="time" required value={itemTime} onChange={event => setItemTime(event.target.value)} /></label>
            <label>照护事项<input required maxLength={120} value={itemTitle} onChange={event => setItemTitle(event.target.value)} /></label>
            <button disabled={busy || !itemTitle.trim()}>添加事项</button>
          </form>
        </article>
        <article className="care-card"><h2>给{data.is_owner ? data.relative_name : data.owner_name}留言</h2>
          <form className="care-form" onSubmit={event => {event.preventDefault(); void act(async () => {
            await post(endpoint + '/messages', {text: note}); setNote('');
          }, '留言已发送');}}>
            <label>留言<textarea required maxLength={500} value={note} onChange={event => setNote(event.target.value)} /></label>
            <button disabled={busy || !note.trim()}>发送留言</button>
          </form>
          <ul className="care-list">{data.messages.map(entry => <li key={entry.id}>
            <small>{entry.sender_name} · {dateText(entry.created_at)} · {entry.read_at ? '已读' : '未读'}</small>
            <p>{entry.text}</p>
            {!entry.mine && !entry.read_at && <button className="secondary" disabled={busy} onClick={() => void act(
              () => post(endpoint + '/messages/' + entry.id + '/read'), '已标记为已读')}>标记已读</button>}
          </li>)}</ul>
        </article>
      </div>}
      {tab === 'alerts' && <div className="care-grid">
        <article className="care-card"><h2>联系与照护人</h2>
          {data.is_owner && <form className="care-form" key={data.callback_phone ?? 'none'} onSubmit={event => {
            event.preventDefault();
            const phone = String(new FormData(event.currentTarget).get('callback') ?? '');
            void act(() => request(endpoint + '/callback', {method: 'PATCH', body: JSON.stringify({phone})}), '回拨电话已更新');
          }}>
            <label>共享回拨电话<input type="tel" name="callback" maxLength={25} defaultValue={data.callback_phone ?? ''} /></label>
            <button disabled={busy}>保存电话</button>
          </form>}
          <ul className="care-list">{data.contacts.map(contact => <li key={contact.id}>
            <strong>{contact.name}</strong> <span>{contact.relation} {Boolean(contact.preferred) && '· 首选'}</span>
            <div className="care-actions">
              <a className="button secondary" href={`tel:${contact.phone}`}>拨号 {contact.phone}</a>
              {data.is_owner && <>
                {!contact.preferred && <button className="secondary" disabled={busy} onClick={() => void act(
                  () => post(endpoint + '/contacts/' + contact.id + '/prefer'), '已设为首选')}>设为首选</button>}
                <button className="secondary" disabled={busy} onClick={() => {
                  if (window.confirm(`移除联系人 ${contact.name}？`)) void act(
                    () => request(endpoint + '/contacts/' + contact.id, {method: 'DELETE'}), '已移除联系人');
                }}>移除</button>
              </>}
            </div>
          </li>)}</ul>
          {!data.contacts.length && <p>暂无已共享的联系人。</p>}
          {data.is_owner && <form className="care-form" onSubmit={submitContact}>
            <label>联系人姓名<input name="name" required maxLength={50} /></label>
            <label>关系<input name="relation" maxLength={40} /></label>
            <label>联系电话<input name="phone" type="tel" required maxLength={25} /></label>
            <button disabled={busy}>添加联系人</button>
          </form>}
        </article>
        <article className="care-card"><h2>记录提示与演练</h2>
          <ul className="care-list">{data.records.filter(record => record.review_level && record.review_level !== 'reference_only').map(record =>
            <li key={record.id}><Link to={`/records/${record.id}`}>{recordTitle(record)}</Link>
              <small>查看这条记录的质量与复核提示</small></li>)}</ul>
          <p className="care-muted">演练提醒只在本应用内显示，不发送短信。</p>
          <button className="secondary" disabled={busy} onClick={() => void act(
            () => post(endpoint + '/drills'), '站内演练已发送')}>发送站内演练</button>
          <ul className="care-list">{data.drills.map(entry => <li key={entry.id}>
            <strong>站内演练 · {entry.acknowledged_at ? '已确认' : '待确认'}</strong>
            <small>{entry.sender_name} · {dateText(entry.created_at)}</small>
            {!entry.mine && !entry.acknowledged_at && <button className="secondary" disabled={busy} onClick={() => void act(
              () => post(endpoint + '/drills/' + entry.id + '/ack'), '已确认收到')}>确认收到</button>}
          </li>)}</ul>
        </article>
      </div>}
    </>}
  </section>;
}
