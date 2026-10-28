"""刘源维护设备适配，王书阁维护记录入口。"""
from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.core.runner import runner
from app.services import records
from hardware.acquisition import device_status, sample

router = APIRouter(prefix='/acquisition', tags=['采集接入'])


@router.get('/status')
def status(user: str = Depends(current_user)):
    return device_status()


@router.post('/replay', status_code=202)
def replay(user: str = Depends(current_user)):
    task = records.submit(user, sample())
    runner.enqueue(task['id'])
    return task
