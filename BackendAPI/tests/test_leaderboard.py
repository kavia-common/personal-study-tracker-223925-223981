from fastapi import status


def test_leaderboard_empty_db(client):
    r = client.get("/leaderboard")
    assert r.status_code == status.HTTP_200_OK, r.text
    data = r.json()
    assert "all_time" in data and "last_30_days" in data
    assert isinstance(data["all_time"], list)
    assert isinstance(data["last_30_days"], list)
    assert data["all_time"] == []
    assert data["last_30_days"] == []


def test_leaderboard_with_seed(client, seed_sessions):
    # Seed data
    seed_sessions()
    # Call leaderboard
    r = client.get("/leaderboard?top=10")
    assert r.status_code == 200, r.text
    body = r.json()

    # Validate structure
    assert "all_time" in body and "last_30_days" in body
    all_time = body["all_time"]
    last_30 = body["last_30_days"]

    # All time totals:
    # u1: 30 + 45 = 75
    # u2: 60 + 15 = 75
    # u3: 10
    # order by total_minutes desc; when ties occur, order between u1/u2 may be stable by DB order.
    assert len(all_time) >= 3
    totals = [entry["total_minutes"] for entry in all_time]
    assert totals[0] >= totals[1]  # non-increasing
    assert set(totals[:3]) == {75, 75, 10}

    # last 30 totals:
    # u1: 45
    # u2: 60 + 15 = 75
    # u3: 0 (excluded)
    assert len(last_30) >= 2
    totals_30 = [entry["total_minutes"] for entry in last_30]
    assert totals_30[0] >= totals_30[1]
    assert set(totals_30[:2]) == {75, 45}
