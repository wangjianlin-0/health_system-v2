from app.api import auth, family, analyze, acquisition, websocket, system
from fastapi import APIRouter

router = APIRouter(prefix='/api/v1')
for module in (auth, family, analyze, acquisition, websocket, system):
    router.include_router(module.router)
