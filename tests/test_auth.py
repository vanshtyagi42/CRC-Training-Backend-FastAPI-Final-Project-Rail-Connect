import re
from datetime import timedelta

from sqlmodel import Session, select

from app.models import PasswordResetToken, User, utcnow
from app.security import hash_token

USER = {"name": "Vansh", "email": "vansh@example.com", "password": "Test@1234"}


def test_register_success(client):
    r = client.post("/auth/register", json=USER)
    assert r.status_code == 201
    assert r.json()["email"] == USER["email"]
    assert "hashed_password" not in r.json()


def test_register_duplicate_email(client):
    client.post("/auth/register", json=USER)
    r = client.post("/auth/register", json=USER)
    assert r.status_code == 409


def test_register_short_password(client):
    r = client.post("/auth/register", json={**USER, "password": "short"})
    assert r.status_code == 422


def test_login_success(client):
    client.post("/auth/register", json=USER)
    r = client.post("/auth/login", json={"email": USER["email"], "password": USER["password"]})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password(client):
    client.post("/auth/register", json=USER)
    r = client.post("/auth/login", json={"email": USER["email"], "password": "WrongPass@1"})
    assert r.status_code == 401


def test_protected_route_without_token(client):
    assert client.get("/users/me").status_code == 401


def test_profile_with_token(client, user_headers):
    r = client.get("/users/me", headers=user_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "user1@example.com"


def test_logout_revokes_token(client, user_headers):
    assert client.get("/users/me", headers=user_headers).status_code == 200
    assert client.post("/auth/logout", headers=user_headers).status_code == 200
    assert client.get("/users/me", headers=user_headers).status_code == 401


def test_reset_password_works_only_once(client, make_user, capsys):
    make_user("reset@example.com")
    capsys.readouterr()  # clear earlier output
    client.post("/auth/forgot-password", json={"email": "reset@example.com"})
    token = re.search(r"Reset token: (\S+)", capsys.readouterr().out).group(1)

    first = client.post("/auth/reset-password", json={"token": token, "new_password": "NewPass@123"})
    assert first.status_code == 200
    second = client.post("/auth/reset-password", json={"token": token, "new_password": "Another@123"})
    assert second.status_code == 400

    new_login = client.post("/auth/login", json={"email": "reset@example.com", "password": "NewPass@123"})
    old_login = client.post("/auth/login", json={"email": "reset@example.com", "password": "Test@1234"})
    assert new_login.status_code == 200
    assert old_login.status_code == 401


def test_reset_password_expired_token(client, engine, make_user):
    make_user("expired@example.com")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "expired@example.com")).first()
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token("expired-token-123"),
                expires_at=utcnow() - timedelta(minutes=1),
            )
        )
        session.commit()
    r = client.post("/auth/reset-password", json={"token": "expired-token-123", "new_password": "NewPass@123"})
    assert r.status_code == 400


def test_forgot_password_unknown_email_same_reply(client):
    r = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200  # does not reveal whether the email exists 