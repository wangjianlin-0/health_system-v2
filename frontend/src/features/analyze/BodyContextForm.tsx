import {useState} from 'react';
import {request} from '../../services/api';

export type BodyContext = {scene: string | null; feeling: string | null};

export default function BodyContextForm({id, context}: {id: string; context?: BodyContext}) {
  const [scene, setScene] = useState(context?.scene ?? '');
  const [feeling, setFeeling] = useState(context?.feeling ?? '');
  const [status, setStatus] = useState('');
  const [saving, setSaving] = useState(false);
  const scenes = [['rest', '静坐休息'], ['after_activity', '刚走动完'], ['other', '其他']];
  const feelings = [['none', '无明显不适'], ['palpitations', '感觉心慌'], ['other', '其他不适']];

  async function save() {
    setSaving(true);
    try {
      await request(`/records/${id}/body-context`, {
        method: 'PATCH', body: JSON.stringify({scene: scene || null, feeling: feeling || null}),
      });
      setStatus('已保存，历史页会使用这次填写的情况。');
    } catch {
      setStatus('保存失败，请重试。');
    } finally {
      setSaving(false);
    }
  }

  return <section className="task-panel body-context-form">
    <h2>测量时的身体状况</h2>
    <div className="body-context-choice-group"><span>当时在做什么</span><div role="group" aria-label="测量场景">
      {scenes.map(([value, label]) => <button type="button" key={value} aria-pressed={scene === value}
        className={scene === value ? 'selected' : ''} onClick={() => setScene(value)}>{label}</button>)}
    </div></div>
    <div className="body-context-choice-group"><span>当时的感受</span><div role="group" aria-label="测量感受">
      {feelings.map(([value, label]) => <button type="button" key={value} aria-pressed={feeling === value}
        className={feeling === value ? 'selected' : ''} onClick={() => setFeeling(value)}>{label}</button>)}
    </div></div>
    <div className="body-context-save"><button type="button" disabled={saving} onClick={() => void save()}>{saving ? '保存中…' : '保存'}</button>
      {status && <p className="body-context-status" role="status">{status}</p>}</div>
  </section>;
}
