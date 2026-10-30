from contextlib import asynccontextmanager
import os
import sqlite3
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure, logger, request_id_var
from app.core.runner import runner
from app.services.records import purge_audit_log, recover_tasks
from app.services.storage import initialize


@asynccontextmanager
async def lifespan(app):
    _guard_single_process()
    configure(settings.log_level)
    info = initialize()
    purged = purge_audit_log()
    recovered = recover_tasks() if settings.recovery_on_start else {'pending': [], 'interrupted': []}
    runner.start()
    for task_id in recovered['pending']:
        runner.enqueue(task_id)
    logger.info(
        '启动完成 schema=%s applied=%s purged_audit=%s recovered_pending=%s interrupted=%s',
        info.get('current'), info.get('applied'), purged,
        len(recovered['pending']), len(recovered['interrupted']),
    )
    try:
        yield
    finally:
        runner.stop()


app = FastAPI(title='家庭心电辅助记录 · 五人协作框架', lifespan=lifespan)
app.include_router(router)


def _guard_single_process() -> None:
    for name in ('WEB_CONCURRENCY', 'UVICORN_WORKERS'):
        raw = (os.environ.get(name) or '').strip()
        if raw.isdigit() and int(raw) > 1:
            raise RuntimeError(
                '当前任务队列为进程内单 worker，请勿设置 WEB_CONCURRENCY/UVICORN_WORKERS>1；'
                '需要多实例时先改为外部任务队列'
            )


@app.middleware('http')
async def request_metadata(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers['X-Request-ID'] = request_id
    logger.info('%s %s -> %s %.1fms request_id=%s', request.method, request.url.path,
                response.status_code, elapsed, request_id)
    return response


def _request_id(request: Request):
    return getattr(request.state, 'request_id', None)


async def app_error(request: Request, error: AppError):
    return JSONResponse(
        {'detail': error.detail, 'code': error.code, 'field': error.field,
         'request_id': _request_id(request)},
        status_code=error.status,
    )


async def domain_error(request: Request, error: Exception):
    status = 401 if isinstance(error, PermissionError) else 404 if isinstance(error, LookupError) \
        else 409 if isinstance(error, sqlite3.IntegrityError) else 400
    code = {401: 'auth_required', 404: 'not_found', 409: 'conflict', 400: 'invalid_request'}[status]
    message = '用户名或记录已存在' if isinstance(error, sqlite3.IntegrityError) else str(error)
    return JSONResponse(
        {'detail': message, 'code': code, 'field': None, 'request_id': _request_id(request)},
        status_code=status,
    )


app.add_exception_handler(AppError, app_error)
for error_type in (ValueError, PermissionError, LookupError, sqlite3.IntegrityError):
    app.add_exception_handler(error_type, domain_error)
