"""记录模块：记录及分析使用流程 HTTP 接口（薄路由，业务在 services.records）。"""
from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth import current_user
from app.core import errors
from app.core.config import settings
from app.core.runner import runner
from app.services import records
from signal_processing.python.ecg_preprocessing import parse_csv

router = APIRouter(tags=['记录与分析'])


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    note: str = Field(default='', max_length=500)


@router.post('/analyze/ecg', status_code=202)
async def upload(response: Response, file: UploadFile = File(...),
                 sample_rate_hz: float = Form(...), user: str = Depends(current_user),
                 idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise ValueError('首版仅支持单列 CSV；WFDB/EDF 解析待信号模块扩展')
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise errors.PayloadTooLarge(f'CSV 最大 {settings.max_upload_bytes // 1_000_000} MB')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('CSV 请使用 UTF-8 编码')
    signal = parse_csv(text, sample_rate_hz)
    task, created = records.submit_task(user, signal, idempotency_key=idempotency_key)
    if created:
        records.store_raw_input(user, task['id'], content)
        runner.enqueue(task['id'])
    else:
        response.status_code = 200
    return task


@router.get('/tasks')
def tasks(status: str | None = None, page: int = Query(default=1, ge=1),
          page_size: int = Query(default=20, ge=1, le=100), user: str = Depends(current_user)):
    return records.list_tasks(user, status, page, page_size)


@router.get('/tasks/{task_id}')
def task(task_id: str, include_events: bool = False, user: str = Depends(current_user)):
    return records.task_status(user, task_id, include_events=include_events)


@router.post('/tasks/{task_id}/cancel')
def cancel(task_id: str, user: str = Depends(current_user)):
    return records.cancel_task(user, task_id)


@router.get('/records')
def listing(shared: bool = False, page: int | None = Query(default=None, ge=1),
            page_size: int = Query(default=20, ge=1, le=100),
            date_from: str | None = Query(default=None, alias='from'),
            date_to: str | None = Query(default=None, alias='to'),
            quality: str | None = None, label: str | None = None, q: str | None = None,
            sort: str = Query(default='created_at_desc'), user: str = Depends(current_user)):
    return records.list_records(user, shared, page, page_size, date_from, date_to,
                                quality, label, q, sort)


@router.get('/records/trends')
def trends(shared: bool = False, days: int = Query(default=30, ge=1, le=365),
           timezone: str = Query(default='UTC'), fill: bool = True,
           user: str = Depends(current_user)):
    return records.trend(user, shared, days, timezone, fill)


@router.get('/records/{identifier}/waveform')
def waveform(identifier: str, start_sec: float | None = Query(default=None, ge=0),
             end_sec: float | None = Query(default=None, gt=0),
             max_points: int = Query(default=2000, ge=100, le=settings.waveform_max_points),
             mode: str = Query(default='envelope', pattern='^(envelope|mean)$'),
             user: str = Depends(current_user)):
    return records.waveform_window(user, identifier, start_sec, end_sec, max_points, mode)


@router.get('/records/{identifier}/raw')
def raw(identifier: str, user: str = Depends(current_user)):
    path, filename = records.raw_file(user, identifier)
    return FileResponse(path, media_type='text/csv; charset=utf-8', filename=filename)


@router.get('/records/{identifier}/access-log')
def access_log(identifier: str, action: str | None = None,
               page: int = Query(default=1, ge=1),
               page_size: int = Query(default=20, ge=1, le=100),
               user: str = Depends(current_user)):
    return records.access_log(user, identifier, action, page, page_size)


@router.post('/records/{identifier}/reanalyze', status_code=202)
def reanalyze(identifier: str, user: str = Depends(current_user)):
    task = records.reanalyze(user, identifier)
    runner.enqueue(task['id'])
    return task


@router.get('/records/{identifier}/export')
def export(identifier: str, format: str = Query(default='csv', pattern='^(csv|json|raw)$'),
           user: str = Depends(current_user)):
    if format == 'raw':
        return raw(identifier, user)
    content, media_type = records.export_record(user, identifier, format)
    filename = f'ecg-record-{identifier}.{format}'
    return Response(content=content, media_type=media_type,
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@router.patch('/records/{identifier}')
def patch(identifier: str, body: NoteUpdate, user: str = Depends(current_user)):
    return records.update_note(user, identifier, body.note)


@router.delete('/records/{identifier}')
def delete(identifier: str, user: str = Depends(current_user)):
    return records.delete_record(user, identifier)


@router.get('/records/{identifier}')
def detail(identifier: str, user: str = Depends(current_user)):
    return records.detail(user, identifier)


@router.get('/analyze/{identifier}')
def analysis_status(identifier: str, user: str = Depends(current_user)):
    return records.detail(user, identifier)
