import {useEffect, useState} from 'react';
import {request} from '../../services/api';
export type BodyContext = {scene: string | null; feeling: string | null};
const scenes = [['rest', '静坐休息'], ['after_activity', '刚走动完']];
const feelings = [['none', '无明显不适'], ['palpitations', '感觉心慌']];
const split = (value?: string | null) => value ? value.split('、').map(item => item.trim()).filter(Boolean) : [];
export function formatBodyContext(value: string | null | undefined, field: 'scene' | 'feeling'): string {
  const labels = Object.fromEntries(field === 'scene' ? scenes : feelings);
  return split(value).map(item => labels[item] ?? item).join('、') || '未填写';
}
export default function BodyContextForm({id, context}: {id: string; context?: BodyContext}) {
  const [scene, setScene] = useState<string[]>(split(context?.scene));
  const [feeling, setFeeling] = useState<string[]>(split(context?.feeling));
  const [sceneDraft, setSceneDraft] = useState('');
  const [feelingDraft, setFeelingDraft] = useState('');
  const [suggestions, setSuggestions] = useState<{scene: string[]; feeling: string[]}>({scene: [], feeling: []});
  const [status, setStatus] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => { request<{scene: string[]; feeling: string[]}>('/records/body-context/suggestions')
    .then(setSuggestions).catch(() => {}); }, []);
  function toggle(value: string, selected: string[], setSelected: (next: string[]) => void) {
    setSelected(selected.includes(value) ? selected.filter(item => item !== value) : [...selected, value]);
  }
  function add(value: string, selected: string[], setSelected: (next: string[]) => void,
               field: 'scene' | 'feeling', clear: (value: string) => void) {
    const item = value.trim().replace(/、/g, ' ');
    if (!item) return;
    if (!selected.includes(item)) setSelected([...selected, item]);
    setSuggestions(previous => ({...previous, [field]: [item, ...previous[field].filter(existing => existing !== item)]}));
    clear('');
  }
  async function save() {
    const sceneValue = scene.join('、');
    const feelingValue = feeling.join('、');
    if (sceneValue.length > 80 || feelingValue.length > 80) {setStatus('每组状况最多 80 字，请减少所选项目。'); return;}
    setSaving(true);
    try {
      await request('/records/' + id + '/body-context', {method: 'PATCH', body: JSON.stringify({scene: sceneValue || null, feeling: feelingValue || null})});
      setStatus('已保存测量时的情况。');
    } catch (caught) {setStatus((caught as Error).message);}
    finally {setSaving(false);}
  }
  function group(label: string, presets: string[][], selected: string[], setSelected: (next: string[]) => void,
                 saved: string[], draft: string, setDraft: (value: string) => void, field: 'scene' | 'feeling') {
    const values = [...presets, ...saved.filter(item => !presets.some(([code]) => code === item)).map(item => [item, item])];
    return <div className="body-context-group"><h3>{label}</h3><div className="body-context-options" role="group" aria-label={label}>
      {values.map(([value, text]) => <button type="button" key={value} aria-pressed={selected.includes(value)}
        className={selected.includes(value) ? 'selected' : ''} onClick={() => toggle(value, selected, setSelected)}>{text}</button>)}
    </div><div className="body-context-add"><input maxLength={80} value={draft} aria-label={`添加${label}`}
      onChange={event => setDraft(event.target.value)} onKeyDown={event => {if (event.key === 'Enter') {event.preventDefault(); add(draft, selected, setSelected, field, setDraft);}}}
      placeholder="填写其他情况，可添加多个" /><button type="button" className="secondary" onClick={() => add(draft, selected, setSelected, field, setDraft)}>添加</button></div></div>;
  }
  return <section className="task-panel body-context-form"><h2>测量时的身体状况</h2><p className="hint">可多选；新增的情况保存后，下次可直接选用。</p>
    {group('当时在做什么', scenes, scene, setScene, suggestions.scene, sceneDraft, setSceneDraft, 'scene')}
    {group('当时的感受', feelings, feeling, setFeeling, suggestions.feeling, feelingDraft, setFeelingDraft, 'feeling')}
    <div className="body-context-save"><button type="button" disabled={saving} onClick={() => void save()}>{saving ? '保存中…' : '保存状况'}</button>
      {status && <p className="body-context-status" role="status">{status}</p>}</div>
  </section>;
}
