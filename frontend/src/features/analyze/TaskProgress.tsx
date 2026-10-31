import { AnalysisTask } from '../../services/api';
import { TaskStatusBadge } from '../../components/badges';

const STAGES: {key: string; label: string}[] = [
  {key: 'queued', label: '排队'},
  {key: 'validating', label: '校验'},
  {key: 'preprocessing', label: '预处理'},
  {key: 'inference', label: '推理'},
  {key: 'explaining', label: '解释'},
  {key: 'finished', label: '完成'},
];

const ERROR_HINTS: Record<string, string> = {
  input_invalid: '请检查文件格式、采样率与数值是否有效。',
  analysis_failed: '分析过程出错，可稍后重试或重新提交。',
  model_unavailable: '当前未接入模型，结果仅包含信号检查。',
  interrupted: '服务重启导致任务中断，请重新提交。',
  cancelled: '任务已取消。',
};

export default function TaskProgress({task, error, onCancel}: {
  task: AnalysisTask | null;
  error: string;
  onCancel: () => void;
}) {
  if (!task) {
    return <div className="task-panel">
      <p role="status">正在查询任务 {error ? '' : '…'}</p>
      {error && <p className="notice notice-error" role="alert">{error}</p>}
    </div>;
  }
  const stageIndex = Math.max(0, STAGES.findIndex(stage => stage.key === task.stage));
  const running = task.status === 'pending' || task.status === 'running';
  return <div className="task-panel">
    <div className="task-head">
      <TaskStatusBadge status={task.status} />
      <span className="mono">{task.id}</span>
      {running && <button className="secondary" onClick={onCancel} disabled={task.cancel_requested}>
        {task.cancel_requested ? '取消请求已发送' : '取消任务'}
      </button>}
    </div>
    <ol className="stage-list" aria-label="分析阶段">
      {STAGES.map((stage, index) => (
        <li key={stage.key} className={index < stageIndex ? 'done' : index === stageIndex ? 'current' : ''}>
          {stage.label}
        </li>
      ))}
    </ol>
    <p className="hint">
      {task.status === 'pending' && '任务已排队，后台执行。可以刷新页面继续查询。'}
      {task.status === 'running' && '分析处理中。可以刷新页面继续查询，或等待自动跳转。'}
      {task.status === 'completed' && '分析完成，正在打开详情…'}
      {task.status === 'failed' && (ERROR_HINTS[task.error_code ?? ''] ?? '分析失败，请重新提交。')}
      {task.status === 'cancelled' && '任务已取消，未保存记录。'}
    </p>
    {task.error && <details><summary>技术详情</summary><pre className="mono-wrap">{task.error}</pre></details>}
    {error && <p className="notice notice-error" role="alert">{error}</p>}
  </div>;
}
