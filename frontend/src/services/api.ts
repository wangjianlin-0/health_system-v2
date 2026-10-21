// 前端共享请求与会话适配。
export interface RecordResult {
  id: string; created_at: string; task_status: string;
  result: {source: string; waveform: number[]; sample_rate_hz: number; unit: string; duration_sec: number;
    quality: {status: string; reasons: string[]; scope: string};
    prediction: {status: string; label: string | null; confidence: number | null; explanation: string};};
}
export interface RecordRow {id: string; created_at: string;}
export interface SessionResponse {token: string; username: string; expires_at: number; expires_in: number;}
export interface Grant {
  id: string; username: string; active: number; status: 'pending'|'accepted'|'declined'|'revoked';
  permissions: string[]; created_at: number; responded_at: number|null;
}
export interface Invitation {
  id: string; owner_username: string; status: 'pending'|'accepted'|'declined';
  permissions: string[]; created_at: number; responded_at: number|null;
}
export interface Notification {
  id: string; grant_id: string; message: string; status: 'unread'|'read'|'dismissed';
  kind: string; created_at: number; read_at: number|null;
}
const base = '/api/v1';

export function saveSession(session: SessionResponse) {
  sessionStorage.setItem('ecg_token', session.token);
  sessionStorage.setItem('ecg_username', session.username);
  sessionStorage.setItem('ecg_expires_at', String(session.expires_at));
}

export function clearSession(reason = '') {
  sessionStorage.removeItem('ecg_token');
  sessionStorage.removeItem('ecg_username');
  sessionStorage.removeItem('ecg_expires_at');
  window.dispatchEvent(new CustomEvent('ecg:logout', {detail: {reason}}));
}

export function hasActiveSession() {
  const token = sessionStorage.getItem('ecg_token');
  const expiresAt = Number(sessionStorage.getItem('ecg_expires_at'));
  return Boolean(token) && (!expiresAt || expiresAt * 1000 > Date.now());
}

export function sessionExpiresAt() {
  return Number(sessionStorage.getItem('ecg_expires_at')) || null;
}

export function currentUsername() {
  return sessionStorage.getItem('ecg_username') || '当前用户';
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = sessionStorage.getItem('ecg_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(base + path, {...options, headers});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) clearSession('登录已过期或会话已失效，请重新登录');
    throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败 (${response.status})`);
  }
  return data as T;
}
export function post<T>(path: string, body: unknown = {}) {return request<T>(path, {method:'POST', body:JSON.stringify(body)});}
