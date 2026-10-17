from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import User
from app.security import hash_password

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin@12345"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine):
    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(client):
    """Returns a function: make_user(email) registers + logs in, returns auth headers."""

    def _make(email: str, password: str = "Test@1234"):
        client.post("/auth/register", json={"name": "Test User", "email": email, "password": password})
        r = client.post("/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make


@pytest.fixture
def user_headers(make_user):
    return make_user("user1@example.com")


@pytest.fixture
def user2_headers(make_user):
    return make_user("user2@example.com")


@pytest.fixture
def admin_headers(client, engine):
    with Session(engine) as session:
        session.add(
            User(
                name="Admin",
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASSWORD),
                is_admin=True,
            )
        )
        session.commit()
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def setup_train(client, admin_headers):
    """Two stations, one train (10 seats) and one run 5 days from today."""
    s1 = client.post("/admin/stations", json={"code": "NDLS", "name": "New Delhi", "city": "Delhi"}, headers=admin_headers).json()
    s2 = client.post("/admin/stations", json={"code": "CNB", "name": "Kanpur Central", "city": "Kanpur"}, headers=admin_headers).json()
    train = client.post(
        "/admin/trains",
        json={
            "number": "12033",
            "name": "Delhi Kanpur Shatabdi",
            "source_id": s1["id"],
            "destination_id": s2["id"],
            "departure_time": "06:00:00",
            "arrival_time": "11:00:00",
            "fare": 850,
            "total_seats": 10,
        },
        headers=admin_headers,
    ).json()
    journey_date = (date.today() + timedelta(days=5)).isoformat()
    run = client.post(
        f"/admin/trains/{train['id']}/runs", json={"journey_date": journey_date}, headers=admin_headers
    ).json()
    return {
        "station_ids": (s1["id"], s2["id"]),
        "train_id": train["id"],
        "run_id": run["id"],
        "date": journey_date,
    } 