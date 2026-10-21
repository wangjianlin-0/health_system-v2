"""李运嘉：家属授权和站内授权提示；外部警报未实现。"""
from fastapi import APIRouter, Depends
from typing import Literal
from pydantic import BaseModel, Field
from app.api.auth import current_user
from app.services import family

router = APIRouter(prefix='/family', tags=['家庭协同'])

class Grant(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    permissions: list[Literal['records:list', 'records:read']] = Field(
        default_factory=lambda: ['records:list', 'records:read']
    )

class PermissionUpdate(BaseModel):
    permissions: list[Literal['records:list', 'records:read']]

class NotificationUpdate(BaseModel):
    status: Literal['read', 'dismissed']

@router.get('/grants')
def grants(user: str = Depends(current_user)):
    return family.grants(user)

@router.post('/grants')
def grant(body: Grant, user: str = Depends(current_user)):
    return family.grant(user, body.username, body.permissions)

@router.patch('/grants/{identifier}')
def update_grant(identifier: str, body: PermissionUpdate, user: str = Depends(current_user)):
    return family.update_permissions(user, identifier, body.permissions)

@router.delete('/grants/{identifier}')
def revoke(identifier: str, user: str = Depends(current_user)):
    return family.revoke(user, identifier)

@router.get('/invitations')
def invitations(user: str = Depends(current_user)):
    return family.invitations(user)

@router.post('/invitations/{identifier}/accept')
def accept(identifier: str, user: str = Depends(current_user)):
    return family.respond(user, identifier, 'accepted')

@router.post('/invitations/{identifier}/decline')
def decline(identifier: str, user: str = Depends(current_user)):
    return family.respond(user, identifier, 'declined')

@router.get('/notifications')
def notifications(user: str = Depends(current_user)):
    return family.notifications(user)

@router.patch('/notifications/{identifier}')
def update_notification(identifier: str, body: NotificationUpdate, user: str = Depends(current_user)):
    return family.update_notification(user, identifier, body.status)
