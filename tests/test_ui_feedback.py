import time

from app.services import storage


def account(client, name):
    credentials = {"username": name, "password": "test-password-123"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 200
    token = client.post("/api/v1/auth/login", json=credentials).json()["token"]
    return {"Authorization": "Bearer " + token}


def completed_record(client, headers, title=None):
    response = client.post("/api/v1/acquisition/replay", headers=headers,
                           json={"title": title} if title is not None else None)
    assert response.status_code == 202
    task_id = response.json()["id"]
    for _ in range(200):
        task = client.get("/api/v1/tasks/" + task_id, headers=headers).json()
        if task["status"] == "completed":
            return task["record"]
        if task["status"] == "failed":
            raise AssertionError(task["error"])
        time.sleep(0.02)
    raise AssertionError("task did not complete")


def test_record_names_and_custom_context_are_persistent_and_owner_only(client):
    owner = account(client, "owner")
    other = account(client, "other")
    first = completed_record(client, owner)
    second = completed_record(client, owner, "晨间测量")
    assert "第1次测量" in first["title"]
    assert second["title"] == "晨间测量"
    path = "/api/v1/records/" + first["id"]
    assert client.patch(path + "/title", headers=other, json={"title": "越权"}).status_code == 404
    assert client.patch(path + "/title", headers=owner, json={"title": "运动后"}).json()["title"] == "运动后"
    assert client.patch(path + "/body-context", headers=owner,
                        json={"scene": "爬楼梯后", "feeling": "有些疲劳"}).status_code == 200
    assert client.get(path, headers=owner).json()["body_context"] == {
        "scene": "爬楼梯后", "feeling": "有些疲劳"}
    assert client.get("/api/v1/records/body-context/suggestions", headers=owner).json() == {"scene": ["爬楼梯后"], "feeling": ["有些疲劳"]}
    assert client.get("/api/v1/records/body-context/suggestions", headers=other).json() == {"scene": [], "feeling": []}
    listed = client.get("/api/v1/records?page=1&page_size=10", headers=owner).json()["items"]
    assert {item["title"] for item in listed} == {"运动后", "晨间测量"}
    assert client.patch(path + "/title", headers=owner, json={"title": ""}).json()["title"].endswith("第1次测量")


def test_profile_updates_and_password_change_require_current_password(client):
    headers = account(client, "profile-owner")
    profile = client.get("/api/v1/auth/profile", headers=headers).json()
    assert profile["avg_heart_rate_bpm"] is None
    response = client.patch("/api/v1/auth/profile", headers=headers,
                            json={"username": "renamed-owner", "age": 42, "sex": "undisclosed"})
    assert response.status_code == 200
    assert response.json()["username"] == "renamed-owner"
    assert response.json()["age"] == 42
    assert client.post("/api/v1/auth/password", headers=headers,
                       json={"current_password": "wrong", "new_password": "new-password-123"}).status_code == 400
    assert client.post("/api/v1/auth/password", headers=headers,
                       json={"current_password": "test-password-123",
                             "new_password": "new-password-123"}).status_code == 200
    assert client.get("/api/v1/auth/profile", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "username": "renamed-owner", "password": "new-password-123"}).status_code == 200





def test_reanalysis_inherits_user_annotations(client):
    headers = account(client, "annotation-owner")
    source = completed_record(client, headers, "晨间记录")
    path = "/api/v1/records/" + source["id"]
    assert client.patch(path + "/body-context", headers=headers,
                        json={"scene": "爬楼梯后、喝咖啡后", "feeling": "疲劳、心慌"}).status_code == 200
    assert client.patch(path, headers=headers, json={"note": "原始备注"}).status_code == 200
    response = client.post(path + "/reanalyze", headers=headers, json={"model_type": "none"})
    assert response.status_code == 202
    for _ in range(200):
        task = client.get("/api/v1/tasks/" + response.json()["id"], headers=headers).json()
        if task["status"] == "completed":
            derived = task["record"]
            break
        if task["status"] == "failed":
            raise AssertionError(task["error"])
        time.sleep(0.02)
    else:
        raise AssertionError("task did not complete")
    assert derived["title"] == "晨间记录（重分析）"
    assert derived["note"] == "原始备注"
    detail = client.get("/api/v1/records/" + derived["id"], headers=headers).json()
    assert detail["root_record_title"] == "晨间记录"
    assert detail["body_context"] == {"scene": "爬楼梯后、喝咖啡后", "feeling": "疲劳、心慌"}
    suggestions = client.get("/api/v1/records/body-context/suggestions", headers=headers).json()
    assert suggestions["scene"] == ["爬楼梯后", "喝咖啡后"]
    assert client.patch("/api/v1/records/" + derived["id"], headers=headers, json={"note": "子记录编辑"}).status_code == 400
    assert client.patch("/api/v1/records/" + derived["id"] + "/body-context", headers=headers,
                        json={"scene": "爬楼梯后", "feeling": "疲劳"}).status_code == 404



def test_reanalysis_chain_uses_first_record_annotations(client):
    headers = account(client, "chain-owner")
    original = completed_record(client, headers, "最初测量")
    root_path = "/api/v1/records/" + original["id"]
    child_task = client.post(root_path + "/reanalyze", headers=headers, json={"model_type": "none"}).json()["id"]
    for _ in range(200):
        task = client.get("/api/v1/tasks/" + child_task, headers=headers).json()
        if task["status"] == "completed":
            child = task["record"]
            break
        time.sleep(0.02)
    else:
        raise AssertionError("child task did not complete")
    grand_task = client.post("/api/v1/records/" + child["id"] + "/reanalyze",
                             headers=headers, json={"model_type": "none"}).json()["id"]
    for _ in range(200):
        task = client.get("/api/v1/tasks/" + grand_task, headers=headers).json()
        if task["status"] == "completed":
            grandchild = task["record"]
            break
        time.sleep(0.02)
    else:
        raise AssertionError("grandchild task did not complete")
    assert client.patch(root_path, headers=headers, json={"note": "后补的备注"}).status_code == 200
    assert client.patch(root_path + "/body-context", headers=headers,
                        json={"scene": "静坐后", "feeling": "无不适"}).status_code == 200
    derived = client.get("/api/v1/records/" + grandchild["id"], headers=headers).json()
    assert derived["root_record_id"] == original["id"]
    assert derived["root_record_title"] == "最初测量"
    assert derived["note"] == "后补的备注"
    assert derived["body_context"] == {"scene": "静坐后", "feeling": "无不适"}
