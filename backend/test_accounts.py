"""
Tests for account creation: sign-up with profile and contact details, and
adding the people you know (app/routes/auth.py and app/routes/connections.py).

Run from the backend folder, with MariaDB running and test data loaded:
    python -m pytest test_accounts.py -v

Accounts created here are deleted afterwards (their contacts, connections and
job openings are deleted with them).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def require_database():
    try:
        db.query("SELECT 1")
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")


@pytest.fixture
def emails():
    """Hands out unique emails; every account made with them is deleted afterwards."""
    made = []

    def new():
        made.append(f"acct-{uuid.uuid4().hex[:12]}@example.com")
        return made[-1]

    yield new
    for email in made:
        db.execute("DELETE FROM users WHERE email = %s", (email,))


def unique_digits():
    return "555" + str(uuid.uuid4().int)[:7]


def signup(email, **extra):
    body = {"email": email, "password": "secret123", "first_name": "Ada", "last_name": "Lovelace"}
    body.update(extra)
    return client.post("/auth/signup", json=body)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def contacts_of(user_id):
    rows = db.query("SELECT contact_type, value, is_public FROM user_contacts WHERE user_id = %s", (user_id,))
    return {r["contact_type"]: r for r in rows}


# ---------------------------------------------------------------------------
# Sign-up with profile and contact details
# ---------------------------------------------------------------------------

def test_minimal_signup_still_works(emails):
    resp = signup(emails())
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["job_title"] is None


def test_signup_saves_profile_and_contacts(emails):
    email = emails()
    digits = unique_digits()
    handle = f"Ada-{uuid.uuid4().hex[:8]}"
    resp = signup(email, job_title="  Software   Engineer ", company="Analytical Engines",
                  location="London", bio="I write programs.\nFor engines.",
                  phone=f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}", github=f"@{handle}")
    assert resp.status_code == 201, resp.text
    user = resp.json()["user"]
    assert user["job_title"] == "Software Engineer"          # extra spaces tidied
    assert user["company"] == "Analytical Engines"
    assert user["location"] == "London"
    assert user["bio"] == "I write programs.\nFor engines."  # line breaks kept in the bio

    contacts = contacts_of(user["id"])
    assert contacts["email"]["value"] == email and not contacts["email"]["is_public"]
    assert contacts["phone"]["value"] == "1" + digits         # digits only
    assert not contacts["phone"]["is_public"]
    assert contacts["github"]["value"] == handle.lower()     # no @, lowercase
    assert contacts["github"]["is_public"]


def test_hiring_manager_can_post_an_open_role(emails):
    resp = signup(emails(), company="Analytical Engines", is_hiring=True, open_role="Backend Engineer")
    assert resp.status_code == 201, resp.text
    user = resp.json()["user"]
    assert user["is_hiring"]
    jobs = db.query("SELECT title, company, is_open FROM job_openings WHERE posted_by = %s", (user["id"],))
    assert jobs == [{"title": "Backend Engineer", "company": "Analytical Engines", "is_open": 1}]


def test_open_role_needs_a_company(emails):
    assert signup(emails(), is_hiring=True, open_role="Backend Engineer").status_code == 400


def test_open_role_ignored_when_not_hiring(emails):
    resp = signup(emails(), company="Acme", is_hiring=False, open_role="Backend Engineer")
    assert resp.status_code == 201
    assert not db.query("SELECT 1 FROM job_openings WHERE posted_by = %s", (resp.json()["user"]["id"],))


def test_same_phone_written_differently_is_a_duplicate(emails):
    digits = unique_digits()
    assert signup(emails(), phone=digits).status_code == 201
    email = emails()
    resp = signup(email, phone=f"({digits[:3]}) {digits[3:6]}-{digits[6:]}")
    assert resp.status_code == 409
    assert "phone" in resp.json()["detail"]
    # The failed sign-up created nothing
    assert not db.query("SELECT 1 FROM users WHERE email = %s", (email,))


def test_us_number_with_and_without_country_code_is_a_duplicate(emails):
    digits = unique_digits()                       # 10 digits
    assert signup(emails(), phone=f"+1 {digits}").status_code == 201
    resp = signup(emails(), phone=f"({digits[:3]}) {digits[3:6]}-{digits[6:]}")
    assert resp.status_code == 409


def test_duplicate_github_ignores_case(emails):
    handle = f"dev-{uuid.uuid4().hex[:8]}"
    assert signup(emails(), github=handle).status_code == 201
    resp = signup(emails(), github=handle.upper())
    assert resp.status_code == 409
    assert "GitHub" in resp.json()["detail"]


@pytest.mark.parametrize("field, value", [
    ("phone", "12345"),                 # too short
    ("phone", "call me maybe"),         # not a number
    ("github", "-starts-with-hyphen"),
    ("github", "double--hyphen"),
    ("github", "x" * 40),               # too long
    ("job_title", "x" * 151),
    ("bio", "x" * 1001),
])
def test_invalid_optional_fields_are_rejected(emails, field, value):
    email = emails()
    assert signup(email, **{field: value}).status_code == 400
    assert not db.query("SELECT 1 FROM users WHERE email = %s", (email,))


def test_blank_optional_fields_are_saved_as_empty(emails):
    resp = signup(emails(), job_title="   ", phone="", github=" ")
    assert resp.status_code == 201
    user = resp.json()["user"]
    assert user["job_title"] is None
    assert set(contacts_of(user["id"])) == {"email"}


# ---------------------------------------------------------------------------
# Adding the people you know
# ---------------------------------------------------------------------------

@pytest.fixture
def new_user(emails):
    """A freshly signed-up user: (user, token)."""
    data = signup(emails(), first_name="New", last_name="Person").json()
    return data["user"], data["token"]


def some_other_users(n, exclude):
    rows = db.query("SELECT id FROM users WHERE id != %s ORDER BY id LIMIT %s", (exclude, n))
    return [r["id"] for r in rows]


def test_new_account_has_no_connections(new_user):
    user, token = new_user
    assert client.get("/me/connections", headers=auth(token)).json() == []


def test_add_list_update_and_remove_a_connection(new_user):
    user, token = new_user
    other = some_other_users(1, user["id"])[0]

    resp = client.post("/me/connections", headers=auth(token),
                       json={"user_id": other, "closeness": 4, "context": " Worked  together at Acme "})
    assert resp.status_code == 201, resp.text
    conn = resp.json()
    assert conn["id"] == other
    assert conn["strength"] == 0.8 and conn["closeness"] == 4
    assert conn["context"] == "Worked together at Acme"
    assert conn["source"] == "self_rated"

    # Stored once, smaller id first, so the graph and the other person see it too
    a, b = sorted((user["id"], other))
    assert db.query("SELECT strength FROM user_connections WHERE user_a_id=%s AND user_b_id=%s", (a, b))

    # Adding the same person again updates the closeness and keeps the context
    resp = client.post("/me/connections", headers=auth(token), json={"user_id": other, "closeness": 2})
    assert resp.json()["strength"] == 0.4
    assert resp.json()["context"] == "Worked together at Acme"
    assert len(client.get("/me/connections", headers=auth(token)).json()) == 1

    assert client.delete(f"/me/connections/{other}", headers=auth(token)).status_code == 204
    assert client.get("/me/connections", headers=auth(token)).json() == []


def test_connections_are_listed_strongest_first(new_user):
    user, token = new_user
    weak, strong = some_other_users(2, user["id"])
    client.post("/me/connections", headers=auth(token), json={"user_id": weak, "closeness": 1})
    client.post("/me/connections", headers=auth(token), json={"user_id": strong, "closeness": 5})
    listed = client.get("/me/connections", headers=auth(token)).json()
    assert [c["id"] for c in listed] == [strong, weak]


def test_connection_errors(new_user):
    user, token = new_user
    other = some_other_users(1, user["id"])[0]
    post = lambda body: client.post("/me/connections", headers=auth(token), json=body)

    assert post({"user_id": user["id"], "closeness": 3}).status_code == 400    # yourself
    assert post({"user_id": 999999999, "closeness": 3}).status_code == 404     # nobody
    assert post({"user_id": other, "closeness": 0}).status_code == 422         # out of range
    assert post({"user_id": other, "closeness": 6}).status_code == 422
    assert post({"user_id": other, "closeness": 3, "context": "x" * 256}).status_code == 422


def test_connections_require_sign_in():
    assert client.get("/me/connections").status_code == 401
    assert client.post("/me/connections", json={"user_id": 1, "closeness": 3}).status_code == 401
    assert client.delete("/me/connections/1").status_code == 401


def test_adding_a_connection_lets_a_new_user_find_paths(new_user):
    """The point of all this: a brand-new account goes from no results to real paths."""
    user, token = new_user
    job = db.query("SELECT title, posted_by FROM job_openings WHERE is_open ORDER BY id LIMIT 1")
    if not job:
        pytest.skip("no open jobs; run the seed script first")
    title, manager = job[0]["title"], job[0]["posted_by"]

    search = lambda: client.get("/search", params={"seeker_id": user["id"], "q": title}).json()["results"]
    assert search() == []                                           # nobody known yet

    client.post("/me/connections", headers=auth(token), json={"user_id": manager, "closeness": 5})
    results = search()
    assert any(r["target_id"] == manager and r["path"] == [user["id"], manager] for r in results)
