"""账户模块：家属邀请确认、授权和站内通知。"""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.api.auth import current_user
from app.services import family, family_care

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


class CareItem(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    due_date: date
    due_time: str = Field(pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')


class CareCheck(BaseModel):
    done: bool


class CareMessage(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class CareContact(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    relation: str = Field(default='', max_length=40)
    phone: str = Field(min_length=6, max_length=25)


class CareCallback(BaseModel):
    phone: str = Field(max_length=25)


@router.get('/care/{grant_id}')
def care_overview(grant_id: str, day: date | None = None, timezone: str = 'UTC',
                  user: str = Depends(current_user)):
    selected = day or date.today()
    if not 2000 <= selected.year <= 2100:
        raise ValueError('日期不在支持范围内')
    return family_care.overview(user, grant_id, selected, timezone)


@router.post('/care/{grant_id}/items', status_code=201)
def care_add_item(grant_id: str, body: CareItem, user: str = Depends(current_user)):
    family_care.add_item(user, grant_id, body.title, body.due_date, body.due_time)


@router.patch('/care/{grant_id}/items/{item_id}', status_code=204)
def care_update_item(grant_id: str, item_id: str, body: CareCheck, user: str = Depends(current_user)):
    family_care.set_item(user, grant_id, item_id, body.done)


@router.post('/care/{grant_id}/messages', status_code=201)
def care_send_message(grant_id: str, body: CareMessage, user: str = Depends(current_user)):
    family_care.send_message(user, grant_id, body.text)


@router.post('/care/{grant_id}/messages/{message_id}/read', status_code=204)
def care_read_message(grant_id: str, message_id: str, user: str = Depends(current_user)):
    family_care.read_message(user, grant_id, message_id)


@router.post('/care/{grant_id}/contacts', status_code=201)
def care_add_contact(grant_id: str, body: CareContact, user: str = Depends(current_user)):
    family_care.save_contact(user, grant_id, body.name, body.relation, body.phone)


@router.post('/care/{grant_id}/contacts/{contact_id}/prefer', status_code=204)
def care_prefer_contact(grant_id: str, contact_id: str, user: str = Depends(current_user)):
    family_care.prefer_contact(user, grant_id, contact_id)


@router.delete('/care/{grant_id}/contacts/{contact_id}', status_code=204)
def care_delete_contact(grant_id: str, contact_id: str, user: str = Depends(current_user)):
    family_care.delete_contact(user, grant_id, contact_id)


@router.patch('/care/{grant_id}/callback', status_code=204)
def care_update_callback(grant_id: str, body: CareCallback, user: str = Depends(current_user)):
    family_care.update_callback(user, grant_id, body.phone)


@router.post('/care/{grant_id}/drills', status_code=201)
def care_send_drill(grant_id: str, user: str = Depends(current_user)):
    family_care.send_drill(user, grant_id)


@router.post('/care/{grant_id}/drills/{drill_id}/ack', status_code=204)
def care_ack_drill(grant_id: str, drill_id: str, user: str = Depends(current_user)):
    family_care.acknowledge_drill(user, grant_id, drill_id)
