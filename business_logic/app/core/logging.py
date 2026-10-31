"""日志与请求上下文；任务线程通过 request_id_var 关联到发起请求。"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar('request_id', default='-')
logger = logging.getLogger('ecg')


def configure(level: str = 'INFO') -> None:
    if logger.handlers:
        logger.setLevel(level.upper())
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
