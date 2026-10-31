import { useEffect, useState } from 'react';
import { AnalysisTask, request } from '../services/api';

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export function useTaskPolling(taskId: string | null) {
  const [task, setTask] = useState<AnalysisTask | null>(null);
  const [error, setError] = useState('');
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      setError('');
      setPolling(false);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    let delay = 800;
    const controller = new AbortController();

    function schedule() {
      if (cancelled) return;
      if (document.hidden) {
        window.addEventListener('visibilitychange', onVisible, {once: true});
        return;
      }
      timer = window.setTimeout(() => {void poll();}, delay);
    }

    function onVisible() {
      if (!document.hidden && !cancelled) void poll();
    }

    async function poll() {
      try {
        const next = await request<AnalysisTask>(`/tasks/${taskId}`, {signal: controller.signal});
        if (cancelled) return;
        setTask(next);
        setError('');
        if (TERMINAL.has(next.status)) {
          setPolling(false);
          return;
        }
        delay = Math.min(Math.round(delay * 1.5), 5000);
        schedule();
      } catch (caught) {
        if (cancelled || (caught as Error).name === 'AbortError') return;
        setError((caught as Error).message);
        delay = Math.min(Math.round(delay * 1.5), 5000);
        schedule();
      }
    }

    setError('');
    setPolling(true);
    void poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer) window.clearTimeout(timer);
      window.removeEventListener('visibilitychange', onVisible);
    };
  }, [taskId]);

  return {task, error, polling};
}
