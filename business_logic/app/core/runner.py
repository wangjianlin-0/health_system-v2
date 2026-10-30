"""进程内任务队列：单写多读，启动恢复 pending，优雅停机。"""
from __future__ import annotations

import queue
import threading

from app.core.config import settings
from app.core.logging import logger


class TaskRunner:
    def __init__(self, workers: int = 1):
        self.workers = max(1, int(workers))
        self.queue: queue.Queue[str] = queue.Queue()
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []

    def start(self) -> None:
        if self.threads:
            return
        self.stop_event.clear()
        self.queue = queue.Queue()
        for index in range(self.workers):
            thread = threading.Thread(target=self._loop, name=f'ecg-task-{index}', daemon=True)
            thread.start()
            self.threads.append(thread)
        logger.info('任务运行器已启动：workers=%s', self.workers)

    def enqueue(self, task_id: str) -> None:
        self.queue.put(task_id)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                task_id = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                from app.services import records
                records.execute(task_id)
            except Exception:  # 单任务失败不能拖垮工作线程
                logger.exception('任务执行异常：task_id=%s', task_id)
            finally:
                self.queue.task_done()

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout)
        self.threads.clear()
        logger.info('任务运行器已停止')


runner = TaskRunner(settings.task_workers)
