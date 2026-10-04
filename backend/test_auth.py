"""
Tests for sign up, sign in and /auth/me (app/routes/auth.py and app/security.py).

Run from the backend folder, with MariaDB running:
    python -m pytest test_auth.py -v

Accounts created here are deleted afterwards.
"""
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db, security
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def require_database():
    try:
        db.query("SELECT 1")
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")


@pytest.fixture
def new_email():
    """A unique email for one test; that account is deleted afterwards."""
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    yield email
    db.execute("DELETE FROM users WHERE email = %s", (email,))   # contacts go with it


def signup(email, password="secret123", first="Test", last="User"):
    return client.post("/auth/signup", json={
        "email": email, "password": password, "first_name": first, "last_name": last})


def me(token):
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# Passwords and tokens
# ---------------------------------------------------------------------------

def test_password_hashing():
    stored = security.hash_password("hunter22")
    assert "hunter22" not in stored                          # never stored as typed
    assert security.verify_password("hunter22", stored)
    assert not security.verify_password("hunter23", stored)
    assert security.hash_password("hunter22") != stored     # random salt each time
    assert not security.verify_password("anything", None)   # seeded users have no password


def test_tokens_round_trip_and_reject_tampering():
    token = security.make_token(42)
    assert security.read_token(token) == 42
    user_id, expires, sig = token.split(".")
    assert security.read_token(f"43.{expires}.{sig}") is None              # changed user
    assert security.read_token(f"{user_id}.{int(expires) + 1}.{sig}") is None  # changed expiry
    assert security.read_token("garbage") is None


def test_expired_tokens_are_rejected(monkeypatch):
    token = security.make_token(42)
    monkeypatch.setattr(time, "time", lambda: 10**12)   # far in the future
    assert security.read_token(token) is None


# ---------------------------------------------------------------------------
# Sign up
# ---------------------------------------------------------------------------

def test_signup_creates_account_and_signs_in(new_email):
    resp = signup(new_email.upper())                     # email is case-insensitive
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == new_email            # stored lowercase
    assert body["user"]["first_name"] == "Test"
    assert "password_hash" not in body["user"]           # never sent to the browser
    assert me(body["token"]).json()["id"] == body["user"]["id"]

    # The password is stored hashed, and the email is also saved as a contact
    stored = db.query("SELECT password_hash FROM users WHERE email = %s", (new_email,))[0]["password_hash"]
    assert stored.startswith("pbkdf2_sha256$")
    assert db.query("SELECT 1 FROM user_contacts WHERE contact_type='email' AND value=%s", (new_email,))


def test_signup_rejects_duplicate_email(new_email):
    assert signup(new_email).status_code == 201
    assert signup(new_email).status_code == 409


def test_signup_validates_input(new_email):
    assert signup("not-an-email").status_code == 400
    assert signup(new_email, password="short").status_code == 400
    assert signup(new_email, password="x" * 73).status_code == 400
    assert signup(new_email, first="  ").status_code == 400
    assert client.post("/auth/signup", json={"email": new_email}).status_code == 422   # missing fields


# ---------------------------------------------------------------------------
# Sign in
# ---------------------------------------------------------------------------

def test_login_with_correct_password(new_email):
    signup(new_email, password="correct-horse")
    resp = client.post("/auth/login", json={"email": f"  {new_email.upper()} ", "password": "correct-horse"})
    assert resp.status_code == 200, resp.text
    assert me(resp.json()["token"]).json()["email"] == new_email


def test_login_rejects_wrong_password_and_unknown_email(new_email):
    signup(new_email, password="correct-horse")
    wrong = client.post("/auth/login", json={"email": new_email, "password": "wrong-horse"})
    unknown = client.post("/auth/login", json={"email": "nobody-" + new_email, "password": "x"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()                # same message: no hint which was wrong


def test_seeded_user_without_password_cannot_log_in():
    rows = db.query("SELECT email FROM users WHERE password_hash IS NULL LIMIT 1")
    if not rows:
        pytest.skip("no seeded users without a password")
    resp = client.post("/auth/login", json={"email": rows[0]["email"], "password": "anything"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------

def test_me_requires_a_valid_token():
    assert client.get("/auth/me").status_code == 401
    assert me("garbage").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Token abc"}).status_code == 401
