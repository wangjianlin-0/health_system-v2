"""硬件模块维护设备适配，记录模块维护记录入口。"""
from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.core.runner import runner
from app.services import records
from hardware.acquisition import sample
from hardware.realtime import acquisition, ports
from app.core.config import settings
from pydantic import BaseModel, Field

router = APIRouter(prefix='/acquisition', tags=['采集接入'])


@router.get('/status')
def status(user: str = Depends(current_user)):
    with acquisition.lock:
        return {'mode': 'pc_bluetooth', 'connected': any(not s.done.is_set() and s.owner == user for s in acquisition.sessions.values()),
                'message': '支持ADS1292R蓝牙串口采集；CNN/HGB在电脑CPU运行'}


class StartCapture(BaseModel):
    port: str = Field(pattern=r'^COM[1-9][0-9]{0,4}$')
    baud: int = 115200
    format: str = 'document_34'
    model: str = 'cnn'


@router.get('/ports')
def available_ports(user: str = Depends(current_user)):
    return {'ports': ports()}


@router.get('/sessions/current')
def current_session(user: str = Depends(current_user)):
    with acquisition.lock:
        found = [s for s in acquisition.sessions.values() if s.owner == user]
        return found[-1].snapshot() if found else None


@router.post('/sessions', status_code=201)
def start_capture(body: StartCapture, user: str = Depends(current_user)):
    try:
        return acquisition.start(user, body.port, body.baud, body.format, body.model,
                                 settings.upload_dir.parent / 'acquisition')
    except OSError as exc:
        raise ValueError('无法打开或保存采集会话，请检查串口占用、驱动及磁盘权限。') from exc


@router.get('/sessions/{sid}')
def capture_status(sid: str, user: str = Depends(current_user)):
    return acquisition.get(user, sid).snapshot()


@router.post('/sessions/{sid}/stop')
def stop_capture(sid: str, user: str = Depends(current_user)):
    return acquisition.get(user, sid).stop()


class CaptureSaveOptions(BaseModel):
    title: str = Field(default='', max_length=80)


@router.post('/sessions/{sid}/save', status_code=202)
def save_capture(sid: str, body: CaptureSaveOptions | None = None, user: str = Depends(current_user)):
    session = acquisition.get(user, sid)
    with session.lock:
        if session.task is None:
            signal = session.signal()
            if body and body.title.strip():
                signal["record_title"] = body.title.strip()
            session.task = records.submit(user, signal, idempotency_key='capture-' + sid)
            records.store_raw_input(user, session.task['id'], (session.directory / 'samples.csv').read_bytes())
            runner.enqueue(session.task['id'])
        return session.task


class ReplayOptions(BaseModel):
    title: str = Field(default="", max_length=80)


@router.post("/replay", status_code=202)
def replay(body: ReplayOptions | None = None, user: str = Depends(current_user)):
    signal = sample()
    if body and body.title.strip():
        signal["record_title"] = body.title.strip()
    task = records.submit(user, signal)
    runner.enqueue(task['id'])
    return task
