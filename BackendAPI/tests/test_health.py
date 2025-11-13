from fastapi import status


def test_healthcheck_ok(client):
    r = client.get("/")
    assert r.status_code == status.HTTP_200_OK, r.text
    body = r.json()
    assert body.get("message") == "Healthy"
    assert body.get("db") == "ok"
