import {FormEvent, useEffect, useState} from 'react';
import {post, request} from '../services/api';

type ProfileData = {username: string; age: number | null; sex: string | null;
  avg_heart_rate_bpm: number | null; heart_rate_record_count: number};
const FONT_KEY = 'ecg_font_scale';
export default function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [username, setUsername] = useState('');
  const [age, setAge] = useState('');
  const [sex, setSex] = useState('');
  const [fontScale, setFontScale] = useState(Number(localStorage.getItem(FONT_KEY) || 100));
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    request<ProfileData>('/auth/profile').then(data => {
      setProfile(data); setUsername(data.username); setAge(data.age?.toString() ?? ''); setSex(data.sex ?? '');
    }).catch(error => setMessage((error as Error).message));
  }, []);
  function changeFont(value: number) {
    setFontScale(value); localStorage.setItem(FONT_KEY, String(value));
    document.documentElement.style.setProperty('--font-scale', String(value / 100));
  }
  async function saveProfile(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      const data = await request<ProfileData>('/auth/profile', {method: 'PATCH',
        body: JSON.stringify({username: username.trim(), age: age ? Number(age) : null, sex: sex || null})});
      setProfile(data); setMessage('个人资料已保存');
    } catch (error) {setMessage((error as Error).message);}
    finally {setBusy(false);}
  }
  async function savePassword(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      await post('/auth/password', {current_password: currentPassword, new_password: newPassword});
      sessionStorage.removeItem('ecg_token');
      window.dispatchEvent(new Event('ecg:logout'));
    } catch (error) {setMessage((error as Error).message);}
    finally {setBusy(false); setCurrentPassword(''); setNewPassword('');}
  }
  return <section className="profile-page">
    <p className="eyebrow">账号与偏好</p><h1>个人中心</h1>
    <p role="status">{message}</p>
    <div className="profile-grid">
      <article><h2>我的资料</h2>
        <form onSubmit={event => void saveProfile(event)}>
          <label>用户名<input required maxLength={80} value={username} onChange={event => setUsername(event.target.value)} /></label>
          <label>年龄（可选）<input type="number" min={1} max={120} value={age} onChange={event => setAge(event.target.value)} /></label>
          <label>性别（可选）<select value={sex} onChange={event => setSex(event.target.value)}>
            <option value="">不填写</option><option value="female">女</option><option value="male">男</option>
            <option value="other">其他</option><option value="undisclosed">不愿透露</option>
          </select></label>
          <button disabled={busy || !profile}>保存资料</button>
        </form></article>
      <article><h2>界面与记录</h2>
        <label>字体大小：{fontScale}%<input type="range" min={85} max={130} step={5}
          value={fontScale} onChange={event => changeFont(Number(event.target.value))} /></label>
      </article>
      <article className="profile-reference"><h2>心率参考</h2>
        <div className="profile-average"><strong>{profile?.avg_heart_rate_bpm ?? '—'}</strong><span>次/分</span>
          <p>近 30 天有心率的 {profile?.heart_rate_record_count ?? 0} 条记录的平均值，仅用于回顾个人变化。</p></div>
        <p>成人安静休息时，常用参考范围为 <strong>60–100 次/分</strong>。</p>
        {profile?.age != null && profile.age < 18
          ? <p className="notice">此处成人参考范围不适用于未成年人，请结合年龄向专业人员咨询。</p>
          : profile?.avg_heart_rate_bpm == null
            ? <p>目前没有足够的心率记录可供参考。</p>
            : <p className={profile.avg_heart_rate_bpm < 60 || profile.avg_heart_rate_bpm > 100 ? 'notice' : 'profile-reference-ok'}>
                {profile.avg_heart_rate_bpm < 60 ? '低于成人静息参考范围' : profile.avg_heart_rate_bpm > 100 ? '高于成人静息参考范围' : '落在成人静息参考范围内'}；仅当这些记录均在安静休息时测得，才适合这样对照。
              </p>}
        <p className="hint">年龄和性别会影响个体心率，但本页混合了不同测量状态，不能据此给出按年龄、性别的“正常/异常”诊断。若持续偏离个人平时水平或伴有不适，请咨询医生。</p>
        <a href="https://www.heart.org/en/healthy-living/exercise-and-physical-activity/fitness-basics/target-heart-rates" target="_blank" rel="noreferrer">查看美国心脏协会静息心率说明 ↗</a>
      </article>
      <article><h2>修改密码</h2>
        <form onSubmit={event => void savePassword(event)}>
          <label>当前密码<input required type="password" autoComplete="current-password" value={currentPassword}
            onChange={event => setCurrentPassword(event.target.value)} /></label>
          <label>新密码<input required type="password" minLength={8} autoComplete="new-password" value={newPassword}
            onChange={event => setNewPassword(event.target.value)} /></label>
          <p className="hint">修改后会退出当前账号，请使用新密码重新登录。</p>
          <button disabled={busy || newPassword.length < 8}>更新密码</button>
        </form></article>
    </div>
  </section>;
}
