import { outcomeLabel, qualityLabel } from '../services/api';

export function QualityBadge({status, score}: {status: string | null; score?: number | null}) {
  const tone = status === 'insufficient' ? 'warn' : status === 'basic_checks_passed' ? 'ok' : 'muted';
  const suffix = score != null ? ` · ${score} 分` : '';
  return <span className={`badge badge-${tone}`}>{qualityLabel(status)}{suffix}</span>;
}

const STATUS_TEXT: Record<string, string> = {
  pending: '排队中',
  running: '处理中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

export function TaskStatusBadge({status}: {status: string}) {
  const tone = status === 'failed' ? 'bad' : status === 'completed' ? 'ok'
    : status === 'cancelled' ? 'muted' : 'info';
  return <span className={`badge badge-${tone}`}>{STATUS_TEXT[status] ?? status}</span>;
}

export function OutcomeBadge({outcome}: {outcome: string | null}) {
  const tone = outcome === 'classified' ? 'ok' : outcome === 'model_unavailable' ? 'muted'
    : outcome === 'skipped_quality' ? 'warn' : 'muted';
  return <span className={`badge badge-${tone}`}>{outcomeLabel(outcome)}</span>;
}

export function OwnerTag({name}: {name?: string | null}) {
  if (!name) return null;
  return <span className="owner-tag">所有者：{name}</span>;
}
