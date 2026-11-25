"""账户模块：家属邀请确认、授权和站内通知。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.api.auth import current_user
from app.services import family

router = APIRouter(prefix='/family', tags=['家庭协同'])

class Grant(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class InvitationResponse(BaseModel):
    accept: bool


@router.get('/invitations')
def invitations(user: str = Depends(current_user)):
    return family.invitations(user)


@router.post('/invitations/{identifier}/respond')
def respond(identifier: str, body: InvitationResponse, user: str = Depends(current_user)):
    return family.respond(user, identifier, body.accept)


@router.delete('/invitations/{identifier}')
def leave(identifier: str, user: str = Depends(current_user)):
    return family.leave(user, identifier)

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
