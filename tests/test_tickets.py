from __future__ import annotations


def make_ticket(client, **overrides):
    payload = {
        "title": "VPN 无法连接",
        "description": "客户端提示认证失败，无法访问内网。",
        "submitter": "alice",
        "final_category": "NETWORK",
        "final_priority": "P2",
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
        "OPEN",
        "IN_PROGRESS",
        "RESOLVED",
        "CLOSED",
        "CANCELLED",
    }


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
    first = make_ticket(client, title="网络故障 A", final_priority="P1")
    make_ticket(
        client,
        title="软件故障 B",
        description="桌面软件闪退。",
        final_category="SOFTWARE_INCIDENT",
        final_priority="P1",
    )

    filtered = client.get(
        "/tickets",
        params={"final_status": "OPEN", "final_category": "NETWORK", "final_priority": "P1", "submitter": "alice"},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [first["id"]]

    for target in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
        response = client.patch(f"/tickets/{first['id']}/status", json={"final_status": target, "actor": "operator"})
        assert response.status_code == 200
        assert response.json()["final_status"] == target

    invalid = client.patch(f"/tickets/{first['id']}/status", json={"final_status": "OPEN", "actor": "operator"})
    assert invalid.status_code == 409

