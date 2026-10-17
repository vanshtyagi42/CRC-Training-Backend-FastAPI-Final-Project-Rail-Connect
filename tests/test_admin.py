def test_admin_can_add_train(client, setup_train): 
    assert setup_train["train_id"] is not None


def test_user_cannot_add_station(client, user_headers):
    r = client.post("/admin/stations", json={"code": "LKO", "name": "Lucknow", "city": "Lucknow"}, headers=user_headers)
    assert r.status_code == 403


def test_admin_route_without_token(client):
    assert client.get("/admin/trains").status_code == 401


def test_same_source_and_destination_rejected(client, admin_headers, setup_train):
    s1 = setup_train["station_ids"][0]
    r = client.post(
        "/admin/trains",
        json={
            "number": "99999", "name": "Loop Express", "source_id": s1, "destination_id": s1,
            "departure_time": "08:00:00", "arrival_time": "09:00:00", "fare": 100, "total_seats": 50,
        },
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_duplicate_train_number_rejected(client, admin_headers, setup_train):
    s1, s2 = setup_train["station_ids"]
    r = client.post(
        "/admin/trains",
        json={
            "number": "12033", "name": "Copy", "source_id": s1, "destination_id": s2,
            "departure_time": "08:00:00", "arrival_time": "09:00:00", "fare": 100, "total_seats": 50,
        },
        headers=admin_headers,
    )
    assert r.status_code == 409


def test_deactivated_train_not_searchable(client, admin_headers, setup_train):
    params = {"source": "NDLS", "destination": "CNB", "date": setup_train["date"]}
    assert len(client.get("/trains/search", params=params).json()["results"]) == 1
    client.patch(f"/admin/trains/{setup_train['train_id']}/deactivate", headers=admin_headers)
    assert client.get("/trains/search", params=params).json()["results"] == []


def test_seats_cannot_exceed_capacity(client, admin_headers, setup_train):
    r = client.patch(
        f"/admin/runs/{setup_train['run_id']}/seats", json={"available_seats": 500}, headers=admin_headers
    )
    assert r.status_code == 409 