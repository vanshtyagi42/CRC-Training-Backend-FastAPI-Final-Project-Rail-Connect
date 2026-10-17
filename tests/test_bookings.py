def search(client, setup_train, source="NDLS", destination="CNB", date=None):
    return client.get(
        "/trains/search",
        params={"source": source, "destination": destination, "date": date or setup_train["date"]},
    )


def seats_left(client, setup_train):
    return search(client, setup_train).json()["results"][0]["available_seats"]


# Search
def test_search_returns_train_and_seats(client, setup_train):
    r = search(client, setup_train)
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["train_number"] == "12033"
    assert result["fare"] == 850
    assert result["available_seats"] == 10


def test_search_unknown_station(client, setup_train):
    assert search(client, setup_train, source="XYZ").status_code == 404


def test_search_same_station(client, setup_train):
    assert search(client, setup_train, destination="NDLS").status_code == 422


def test_search_past_date(client, setup_train):
    assert search(client, setup_train, date="2020-01-01").status_code == 400


def test_search_no_trains(client, setup_train):
    r = search(client, setup_train, date="2099-01-01")
    assert r.status_code == 200
    assert r.json()["results"] == []
    assert "No trains found" in r.json()["message"]


# Booking
def test_booking_gives_pnr_and_reduces_seats(client, setup_train, user_headers):
    r = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 2}, headers=user_headers)
    assert r.status_code == 201
    body = r.json()
    assert len(body["pnr"]) == 10 and body["pnr"].isdigit()
    assert body["status"] == "CONFIRMED"
    assert body["total_fare"] == 1700
    assert seats_left(client, setup_train) == 8


def test_booking_requires_login(client, setup_train):
    r = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 1})
    assert r.status_code == 401


def test_booking_more_than_available_fails(client, setup_train, user_headers):
    for _ in range(2): 
        client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 5}, headers=user_headers)
    assert seats_left(client, setup_train) == 0
    r = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 1}, headers=user_headers)
    assert r.status_code == 409


def test_last_seat_goes_to_only_one_booking(client, setup_train, user_headers, user2_headers):
    for _ in range(3):  
        client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 3}, headers=user_headers)
    first = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 1}, headers=user_headers)
    second = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 1}, headers=user2_headers)
    assert first.status_code == 201
    assert second.status_code == 409
    assert seats_left(client, setup_train) == 0


def test_booking_invalid_seat_count(client, setup_train, user_headers):
    r = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 7}, headers=user_headers)
    assert r.status_code == 422


def test_booking_unknown_run(client, user_headers):
    r = client.post("/bookings", json={"run_id": 9999, "seats": 1}, headers=user_headers)
    assert r.status_code == 404


# View / history 
def test_view_booking_and_history(client, setup_train, user_headers):
    pnr = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 1}, headers=user_headers).json()["pnr"]
    assert client.get(f"/bookings/{pnr}", headers=user_headers).status_code == 200
    history = client.get("/users/me/bookings", headers=user_headers).json()
    assert [b["pnr"] for b in history] == [pnr]


# Cancellation
def test_cancel_restores_seats(client, setup_train, user_headers):
    pnr = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 3}, headers=user_headers).json()["pnr"]
    assert seats_left(client, setup_train) == 7
    r = client.post(f"/bookings/{pnr}/cancel", headers=user_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"
    assert seats_left(client, setup_train) == 10


def test_second_cancel_does_not_release_seats_again(client, setup_train, user_headers):
    pnr = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 3}, headers=user_headers).json()["pnr"]
    client.post(f"/bookings/{pnr}/cancel", headers=user_headers)
    again = client.post(f"/bookings/{pnr}/cancel", headers=user_headers)
    assert again.status_code == 409
    assert seats_left(client, setup_train) == 10  


# Privacy 
def test_other_user_cannot_view_or_cancel(client, setup_train, user_headers, user2_headers):
    pnr = client.post("/bookings", json={"run_id": setup_train["run_id"], "seats": 2}, headers=user_headers).json()["pnr"]
    assert client.get(f"/bookings/{pnr}", headers=user2_headers).status_code == 404
    assert client.post(f"/bookings/{pnr}/cancel", headers=user2_headers).status_code == 404
    assert client.get("/users/me/bookings", headers=user2_headers).json() == []
    assert seats_left(client, setup_train) == 8 