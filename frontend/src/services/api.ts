// 共享请求适配；各业务页面由对应负责人维护。
export interface QualityInfo {
  status: string;
  reasons: string[];
  scope: string;
  score?: number | null;
  grade?: string | null;
}
export interface HeartRate {
  bpm: number;
  min_bpm?: number;
  max_bpm?: number;
  rr_cv?: number;
  regularity?: string;
}
export interface Prediction {
  status: string;
  label: string | null;
  confidence: number | null;
  model_version?: string | null;
  explanation: string;
  heart_rate?: HeartRate | null;
  beats?: {count: number; vpc_count?: number} | null;
  explanation_detail?: {
    elderly_summary?: string;
    professional_interpretation?: string;
    evidence?: string[];
    uncertainty?: string[];
    reassurance?: string;
    next_steps?: string[];
    risk_level?: string;
    provider?: string;
  } | null;
}
export interface EcgResult {
  source: string;
  waveform: number[];
  sample_rate_hz: number;
  unit: string;
  duration_sec: number;
  lead?: string | null;
  quality: QualityInfo;
  prediction: Prediction;
  mode?: string;
  processing_version?: string;
  heart_rate_bpm?: number | null;
}
export interface WaveformPoint {t: number; v: number;}
export interface WaveformWindow {
  record_id: string;
  sample_rate_hz: number;
  unit: string;
  total_samples: number;
  start_sec: number;
  end_sec: number;
  returned_points: number;
  mode: string;
  points: WaveformPoint[];
}
export interface RecordSummary {
  id: string;
  created_at: string;
  updated_at: string;
  task_id: string | null;
  source: string | null;
  lead: string | null;
  unit: string | null;
  sample_rate_hz: number | null;
  duration_sec: number | null;
  n_samples: number | null;
  quality_status: string | null;
  quality_score: number | null;
  label: string | null;
  confidence: number | null;
  heart_rate_bpm: number | null;
  model_version: string | null;
  processing_version: string | null;
  note: string | null;
  supersedes_record_id: string | null;
  owner_username?: string | null;
}
export interface RecordDetail extends RecordSummary {
  task_status: string;
  result: EcgResult;
  owned?: boolean;
  has_raw_file?: boolean;
}
export type RecordResult = RecordDetail;
export interface RecordPage {items: RecordSummary[]; page: number; page_size: number; total: number; pages: number; shared: boolean;}
export interface RecordTrendPoint {
  date: string;
  records: number;
  quality: Record<string, number>;
  classified: number;
  heart_rate_bpm: number | null;
  heart_rate_min_bpm: number | null;
  heart_rate_max_bpm: number | null;
}
export interface TrendSummary {
  total: number;
  classified: number;
  insufficient: number;
  heart_rate_days: number;
  avg_heart_rate_bpm: number | null;
  last_record_at: string | null;
}
export interface RecordTrends {
  days: RecordTrendPoint[];
  days_requested: number;
  timezone: string;
  shared: boolean;
  summary: TrendSummary;
}
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export interface AnalysisTask {
  id: string;
  status: TaskStatus;
  stage: string | null;
  outcome: string | null;
  error: string | null;
  error_code: string | null;
  record_id: string | null;
  source: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested: boolean;
  processing_version: string;
  source_record_id: string | null;
  duration_ms: number | null;
  record?: RecordDetail | null;
}
export interface TaskPage {items: AnalysisTask[]; page: number; page_size: number; total: number; pages: number;}
export interface Grant {id: string; username: string; active: number;}
export interface Notification {id: string; message: string; status: string;}

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;

  constructor(message: string, status: number, code = 'request_failed', requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

const base = '/api/v1';

function authHeaders(): Headers {
  const headers = new Headers();
  const token = sessionStorage.getItem('ecg_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

function handleUnauthorized(status: number) {
  if (status === 401) {
    sessionStorage.removeItem('ecg_token');
    window.dispatchEvent(new Event('ecg:logout'));
  }
}

function errorFrom(data: unknown, status: number, requestId?: string): ApiError {
  const body = data as {detail?: unknown; code?: unknown} | null;
  const message = typeof body?.detail === 'string' ? body.detail : `请求失败 (${status})`;
  const code = typeof body?.code === 'string' ? body.code : 'request_failed';
  return new ApiError(message, status, code, requestId);
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = sessionStorage.getItem('ecg_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(base + path, {...options, headers});
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {data = JSON.parse(text);} catch {data = null;}
  }
  if (!response.ok) {
    handleUnauthorized(response.status);
    throw errorFrom(data, response.status, response.headers.get('X-Request-ID') ?? undefined);
  }
  return data as T;
}

export function post<T>(path: string, body: unknown = {}) {
  return request<T>(path, {method: 'POST', body: JSON.stringify(body)});
}

export function uploadWithProgress<T>(path: string, body: FormData,
  onProgress?: (percent: number) => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', base + path);
    const token = sessionStorage.getItem('ecg_token');
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = event => {
      if (event.lengthComputable && onProgress) onProgress(Math.round(event.loaded / event.total * 100));
    };
    xhr.onerror = () => reject(new ApiError('网络错误，请检查连接', 0, 'network_error'));
    xhr.onload = () => {
      let data: unknown = null;
      try {data = xhr.responseText ? JSON.parse(xhr.responseText) : null;} catch {data = null;}
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as T);
      handleUnauthorized(xhr.status);
      reject(errorFrom(data, xhr.status));
    };
    xhr.send(body);
  });
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(base + path, {headers: authHeaders()});
  if (!response.ok) {
    let data: unknown = null;
    try {data = await response.json();} catch {data = null;}
    handleUnauthorized(response.status);
    throw errorFrom(data, response.status);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function localTimezone(): string {
  try {return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';} catch {return 'UTC';}
}

export function qualityLabel(status: string | null): string {
  if (status === 'basic_checks_passed') return '基础检查通过';
  if (status === 'insufficient') return '信号质量不足';
  if (!status) return '质量未知';
  return status;
}

export function outcomeLabel(outcome: string | null): string {
  if (outcome === 'classified') return '已分类';
  if (outcome === 'skipped_quality') return '质量不足，未分类';
  if (outcome === 'model_unavailable') return '未接入模型';
  if (outcome === 'unknown') return '结果未知';
  return outcome || '—';
}
