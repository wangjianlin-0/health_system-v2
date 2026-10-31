"""账户模块：家属授权和站内授权提示；外部警报未实现。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.api.auth import current_user
from app.services import family

router = APIRouter(prefix='/family', tags=['家庭协同'])

class Grant(BaseModel):
    username: str = Field(min_length=1, max_length=80)

@router.get('/grants')
def grants(user: str = Depends(current_user)):
    return family.grants(user)

@router.post('/grants')
def grant(body: Grant, user: str = Depends(current_user)):
    return family.grant(user, body.username)

@router.delete('/grants/{identifier}')
def revoke(identifier: str, user: str = Depends(current_user)):
    return family.revoke(user, identifier)

@router.get('/notifications')
def notifications(user: str = Depends(current_user)):
    return family.notifications(user)
