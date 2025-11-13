from datetime import date, timedelta
from fastapi import status


def test_create_list_update_delete_sessions_flow(client, auth_headers):
    headers = auth_headers("charlie@example.com", "Passw0rd!")
    today = date.today()

    # Create session
    create_payload = {"topic": "Algorithms", "minutes": 50, "session_date": today.isoformat()}
    cr = client.post("/sessions", json=create_payload, headers=headers)
    assert cr.status_code == status.HTTP_200_OK, cr.text
    created = cr.json()
    assert created["topic"] == "Algorithms"
    assert created["minutes"] == 50
    assert created["session_date"] == today.isoformat()
    assert "id" in created
    sid = created["id"]

    # List sessions - should include the one we just created; totals should reflect minutes
    lr = client.get("/sessions", headers=headers)
    assert lr.status_code == 200, lr.text
    listing = lr.json()
    assert listing["total"] == 1
    assert listing["total_minutes"] == 50
    assert listing["page"] == 1 and listing["size"] == 20
    assert len(listing["items"]) == 1
    assert listing["items"][0]["id"] == sid

    # Create another to test totals and pagination params
    create_payload2 = {"topic": "Data Structures", "minutes": 30, "session_date": (today - timedelta(days=1)).isoformat()}
    cr2 = client.post("/sessions", json=create_payload2, headers=headers)
    assert cr2.status_code == 200
    # Check totals and ordering (by session_date desc, then created_at desc)
    lr2 = client.get("/sessions?page=1&size=10", headers=headers)
    assert lr2.status_code == 200
    listing2 = lr2.json()
    assert listing2["total"] == 2
    assert listing2["total_minutes"] == 80
    assert [item["topic"] for item in listing2["items"]] == ["Algorithms", "Data Structures"]

    # Update the first session
    update_payload = {"topic": "Advanced Algorithms", "minutes": 60, "session_date": today.isoformat()}
    ur = client.put(f"/sessions/{sid}", json=update_payload, headers=headers)
    assert ur.status_code == 200, ur.text
    updated = ur.json()
    assert updated["topic"] == "Advanced Algorithms"
    assert updated["minutes"] == 60

    # Re-list to confirm totals changed
    lr3 = client.get("/sessions", headers=headers)
    assert lr3.status_code == 200
    listing3 = lr3.json()
    assert listing3["total"] == 2
    assert listing3["total_minutes"] == 90

    # Delete first session
    dr = client.delete(f"/sessions/{sid}", headers=headers)
    assert dr.status_code == status.HTTP_204_NO_CONTENT, dr.text

    # List confirms deletion
    lr4 = client.get("/sessions", headers=headers)
    assert lr4.status_code == 200
    listing4 = lr4.json()
    assert listing4["total"] == 1
    assert listing4["total_minutes"] == 30
    assert len(listing4["items"]) == 1
    assert listing4["items"][0]["topic"] == "Data Structures"


def test_sessions_filters_topic_and_dates(client, auth_headers):
    headers = auth_headers("dana@example.com", "Passw0rd!")
    today = date.today()
    yesterday = today - timedelta(days=1)
    client.post("/sessions", json={"topic": "Math Algebra", "minutes": 20, "session_date": yesterday.isoformat()}, headers=headers)
    client.post("/sessions", json={"topic": "Math Geometry", "minutes": 25, "session_date": today.isoformat()}, headers=headers)
    client.post("/sessions", json={"topic": "History", "minutes": 15, "session_date": today.isoformat()}, headers=headers)

    # Filter by topic contains 'Math'
    r1 = client.get("/sessions?topic=Math", headers=headers)
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["total"] == 2
    assert data1["total_minutes"] == 45
    assert all("Math" in item["topic"] for item in data1["items"])

    # Filter by start_date today -> only two
    r2 = client.get(f"/sessions?start_date={today.isoformat()}", headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["total"] == 2
    assert data2["total_minutes"] == 40

    # Filter by end_date yesterday -> only one
    r3 = client.get(f"/sessions?end_date={yesterday.isoformat()}", headers=headers)
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["total"] == 1
    assert data3["total_minutes"] == 20
