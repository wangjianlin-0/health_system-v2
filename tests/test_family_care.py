from datetime import datetime, timezone

from test_api_flow import account, wait_task
from test_family_invitations import invite, respond


def test_care_records_follow_accepted_grant_and_stop_on_revoke(client):
    owner, relative, outsider = [account(client, name) for name in ('owner', 'relative', 'outsider')]
    grant_id = invite(client, owner, 'relative')
    path = f'/api/v1/family/care/{grant_id}'
    assert client.get(path, headers=relative).status_code == 404
    assert respond(client, relative, grant_id).status_code == 200

    for user in (owner, outsider):
        task = client.post('/api/v1/acquisition/replay', headers=user, json={})
        assert task.status_code == 202
        wait_task(client, user, task.json()['id'])

    care = client.get(path, headers=relative).json()
    assert care['record_count'] == 1
    assert sum(day['count'] for day in care['week']) == 1
    record_id = care['records'][0]['id']
    wave_path = f'/api/v1/records/{record_id}/waveform?start_sec=0&end_sec=10'
    assert client.get(wave_path, headers=relative).status_code == 200
    assert client.get(path, headers=outsider).status_code == 404

    assert client.delete('/api/v1/family/grants/' + grant_id, headers=owner).status_code == 200
    assert client.get(path, headers=relative).status_code == 404
    assert client.get(wave_path, headers=relative).status_code == 404
    assert client.post(path + '/messages', headers=relative, json={'text': '已撤回'}).status_code == 404


def test_care_feedback_and_contact_ownership(client):
    owner, relative, outsider = [account(client, name) for name in ('owner', 'relative', 'outsider')]
    grant_id = invite(client, owner, 'relative')
    assert respond(client, relative, grant_id).status_code == 200
    path = f'/api/v1/family/care/{grant_id}'
    today = datetime.now(timezone.utc).date().isoformat()

    assert client.post(path + '/items', headers=relative, json={
        'title': '记录一次测量', 'due_date': today, 'due_time': '08:30',
    }).status_code == 201
    item = client.get(path, headers=owner).json()['items'][0]
    assert client.patch(path + '/items/' + item['id'], headers=owner, json={'done': True}).status_code == 204
    assert client.get(path, headers=relative).json()['items'][0]['done'] == 1

    assert client.post(path + '/messages', headers=relative, json={'text': '我已查看这次记录。'}).status_code == 201
    note = client.get(path, headers=owner).json()['messages'][0]
    assert note['text'] == '我已查看这次记录。'
    mark_read = path + '/messages/' + note['id'] + '/read'
    assert client.post(mark_read, headers=relative).status_code == 404
    assert client.post(mark_read, headers=owner).status_code == 204
    assert client.get(path, headers=relative).json()['messages'][0]['read_at']

    contact = {'name': '演示联系人', 'relation': '家属', 'phone': '+1 202 555 0110'}
    assert client.post(path + '/contacts', headers=relative, json=contact).status_code == 404
    assert client.post(path + '/contacts', headers=owner, json=contact).status_code == 201
    saved = client.get(path, headers=relative).json()['contacts'][0]
    assert saved['phone'] == '+12025550110'
    assert client.post(path + '/contacts/' + saved['id'] + '/prefer', headers=owner).status_code == 204
    assert client.patch(path + '/callback', headers=outsider, json={'phone': contact['phone']}).status_code == 404
    assert client.patch(path + '/callback', headers=owner, json={'phone': contact['phone']}).status_code == 204
    view = client.get(path, headers=relative).json()
    assert view['callback_phone'] == saved['phone'] and view['contacts'][0]['preferred'] == 1

    assert client.post(path + '/drills', headers=relative).status_code == 201
    drill = client.get(path, headers=owner).json()['drills'][0]
    assert client.post(path + '/drills', headers=relative).status_code == 400
    assert client.post(path + '/drills/' + drill['id'] + '/ack', headers=owner).status_code == 204
    assert client.get(path, headers=relative).json()['drills'][0]['acknowledged_at']
