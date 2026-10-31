// 记录模块：记录与分析页面；模型模块提供统一分析结果。
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  AnalysisTask, RecordDetail as RecordDetailType, post, request, uploadWithProgress,
} from '../services/api';
import { useTaskPolling } from '../hooks/useTaskPolling';
import UploadForm from '../features/analyze/UploadForm';
import TaskProgress from '../features/analyze/TaskProgress';
import RecordDetail from '../features/analyze/RecordDetail';

export default function Analyze() {
  const {id} = useParams();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const taskId = id ? null : search.get('task');
  const {task, error: pollError} = useTaskPolling(taskId);
  const [record, setRecord] = useState<RecordDetailType | null>(null);
  const [recordError, setRecordError] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (task?.status === 'completed' && task.record_id) {
      navigate('/records/' + task.record_id, {replace: true});
    }
  }, [task, navigate]);

  useEffect(() => {
    if (!id) {
      setRecord(null);
      setRecordError('');
      return;
    }
    let active = true;
    setRecord(null);
    setRecordError('');
    request<RecordDetailType>('/records/' + id)
      .then(next => {if (active) setRecord(next);})
      .catch(caught => {if (active) setRecordError((caught as Error).message);});
    return () => {active = false;};
  }, [id]);

  async function submitFile(file: File, rate: number) {
    setBusy(true);
    setProgress(0);
    setSubmitError('');
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('sample_rate_hz', String(rate));
      const next = await uploadWithProgress<AnalysisTask>('/analyze/ecg', body, setProgress);
      setProgress(100);
      setSearch({task: next.id});
    } catch (caught) {
      setSubmitError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function replay() {
    setBusy(true);
    setSubmitError('');
    try {
      const next = await post<AnalysisTask>('/acquisition/replay');
      setSearch({task: next.id});
    } catch (caught) {
      setSubmitError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelTask() {
    if (!taskId) return;
    setSubmitError('');
    try {
      await post('/tasks/' + taskId + '/cancel');
    } catch (caught) {
      setSubmitError((caught as Error).message);
    }
  }

  async function removeRecord() {
    if (!record) return;
    if (!window.confirm('确定删除这条记录吗？删除后不能恢复。')) return;
    setDeleting(true);
    setRecordError('');
    try {
      await request(`/records/${record.id}`, {method: 'DELETE'});
      navigate('/records', {replace: true});
    } catch (caught) {
      setRecordError((caught as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  if (id) {
    return <section>
      <p className="eyebrow">记录与分析</p>
      {recordError && <div className="notice notice-error" role="alert">
        <p>{recordError}</p>
        <p><Link to="/records">返回记录列表</Link></p>
      </div>}
      {!record && !recordError && <p role="status">加载记录…</p>}
      {record && <RecordDetail record={record} onDelete={() => void removeRecord()}
                               onBack={() => navigate('/records')} deleting={deleting} />}
    </section>;
  }

  if (taskId) {
    return <section>
      <p className="eyebrow">记录与分析</p>
      <h1>分析任务</h1>
      <TaskProgress task={task} error={pollError || submitError} onCancel={() => void cancelTask()} />
      <div className="actions">
        <button className="secondary" onClick={() => {setSearch({}); setSubmitError('');}}>返回导入</button>
        <Link className="button secondary" to="/records">查看历史记录</Link>
      </div>
      <p className="hint">任务编号会保留在地址栏，刷新页面可继续查询。</p>
    </section>;
  }

  return <section>
    <p className="eyebrow">记录与分析</p>
    <h1>新建记录</h1>
    <UploadForm onSubmit={(file, rate) => void submitFile(file, rate)}
                onReplay={() => void replay()} busy={busy} progress={progress} error={submitError} />
  </section>;
}
