"""账户模块：身份模块 HTTP 接口。"""
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from app.services import family

router = APIRouter(prefix='/auth', tags=['身份'])
bearer = HTTPBearer(auto_error=False)

class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=256)

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise PermissionError('请登录')
    return family.authenticate(credentials.credentials)

@router.post('/register')
def register(body: Credentials):
    return family.register(body.username, body.password)

@router.post('/login')
def login(body: Credentials):
    return family.login(body.username, body.password)

@router.post('/logout')
def logout(user: str = Depends(current_user), credentials=Depends(bearer)):
    return family.logout(credentials.credentials)
