from __future__ import annotations


def make_ticket(client, **overrides):
    payload = {
        "title": "VPN 无法连接",
        "description": "客户端提示认证失败，无法访问内网。",
        "submitter": "alice",
    }
    payload.update(overrides)
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_seed_is_idempotent_and_exposes_multiple_statuses(client):
    first = client.post("/system/seed")
    second = client.post("/system/seed")

    assert first.status_code == 200
    assert first.json() == {"created": 5, "existing": 0}
    assert second.json() == {"created": 0, "existing": 5}
    tickets = client.get("/tickets", params={"limit": 10}).json()
    assert {ticket["final_status"] for ticket in tickets} == {
        "待处理",
        "处理中",
        "已解决",
        "已关闭",
        "已取消",
    }


def test_ticket_list_declares_utf8_json_for_windows_powershell(client):
    client.post("/system/seed")

    response = client.get("/tickets", params={"limit": 1})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"


def test_crud_soft_delete_and_history(client):
    ticket = make_ticket(client)

    updated = client.patch(f"/tickets/{ticket['id']}", json={"title": "VPN 认证仍无法连接"})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    history = client.get(f"/tickets/{ticket['id']}/events")
    assert history.status_code == 200
    assert [event["event_type"] for event in history.json()] == ["TICKET_CREATED", "TICKET_UPDATED"]

    deleted = client.delete(f"/tickets/{ticket['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/tickets/{ticket['id']}").status_code == 404


def test_validation_and_duplicate_protection(client):
    invalid = client.post("/tickets", json={"title": "", "description": "x", "submitter": "alice"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"

    premature_triage = client.post(
        "/tickets",
        json={
            "title": "不应在创建时分诊",
            "description": "最终分类和优先级应在人工审核 AI 建议后写入。",
            "submitter": "alice",
            "final_category": "网络问题",
            "final_priority": "P2",
        },
    )
    assert premature_triage.status_code == 422
    assert premature_triage.json()["code"] == "validation_error"

    first = make_ticket(client, title="打印机没有墨", description="三楼打印机需要补墨。")
    duplicate = client.post(
        "/tickets",
        json={"title": "打印机没有墨", "description": "三楼打印机需要补墨。", "submitter": "bob"},
    )
    assert duplicate.status_code == 409
    assert str(first["id"]) in duplicate.json()["message"]

    allowed = client.post(
        "/tickets",
        json={
            "title": "打印机没有墨",
            "description": "三楼打印机需要补墨。",
            "submitter": "bob",
            "allow_duplicate": True,
        },
    )
    assert allowed.status_code == 201


def test_combined_filters_and_status_machine(client):
    first = make_ticket(client, title="网络故障 A")
    seeded = client.post("/system/seed")
    assert seeded.status_code == 200

    filtered = client.get(
        "/tickets",
        params={"final_status": "已解决", "final_category": "网络问题", "final_priority": "P1", "submitter": "王强"},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["title"] == "研发网络间歇中断"

    for target in ("处理中", "已解决", "已关闭"):
        response = client.patch(f"/tickets/{first['id']}/status", json={"final_status": target, "actor": "operator"})
        assert response.status_code == 200
        assert response.json()["final_status"] == target

    invalid = client.patch(f"/tickets/{first['id']}/status", json={"final_status": "待处理", "actor": "operator"})
    assert invalid.status_code == 409
