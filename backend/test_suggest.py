"""
Tests for search-as-you-type: /search/suggest, search_type="all", and manager_id.

Run from the backend folder, with MariaDB running:
    python -m pytest test_suggest.py -v

Creates its own small set of people (with made-up, unique names) and deletes
them afterwards, so results don't depend on the seeded test data.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def world():
    """
    seeker --(close)--> alpha (hiring, posts "<Tag> Wrangler")
    seeker --(close)--> beta  (hiring, posts "Chief <Tag> Officer" and "Night Baker")
    gamma: hiring, no open job, connected to seeker
    """
    try:
        db.query("SELECT 1")
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")

    tag = "Zq" + uuid.uuid4().hex[:6]          # unique word to search for
    made = []

    def signup(first, last, **extra):
        email = f"sugg-{uuid.uuid4().hex[:10]}@example.com"
        made.append(email)
        resp = client.post("/auth/signup", json={
            "email": email, "password": "secret123", "first_name": first, "last_name": last, **extra})
        assert resp.status_code == 201, resp.text
        return resp.json()

    seeker = signup("Seeker", "Person")
    alpha = signup(tag, "Alpha", company="Alpha Co", is_hiring=True, open_role=f"{tag} Wrangler")
    beta = signup("Beta", "Person", company="Beta Co", is_hiring=True, open_role=f"Chief {tag} Officer")
    gamma = signup("Gamma", tag, is_hiring=True)
    db.execute("INSERT INTO job_openings (posted_by, title, company) VALUES (%s, 'Night Baker', 'Beta Co')",
               (beta["user"]["id"],))
    headers = {"Authorization": f"Bearer {seeker['token']}"}
    for other in (alpha, beta, gamma):
        client.post("/me/connections", headers=headers, json={"user_id": other["user"]["id"], "closeness": 5})

    yield {"tag": tag, "seeker": seeker["user"]["id"],
           "alpha": alpha["user"]["id"], "beta": beta["user"]["id"], "gamma": gamma["user"]["id"]}

    for email in made:
        db.execute("DELETE FROM users WHERE email = %s", (email,))


def suggest(q, **params):
    resp = client.get("/search/suggest", params={"q": q, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


def search(world, q, **params):
    resp = client.get("/search", params={"seeker_id": world["seeker"], "q": q, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()["results"]


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def test_suggests_roles_with_openings_best_match_first(world):
    roles = suggest(world["tag"].lower())["roles"]          # case doesn't matter
    titles = [r["title"] for r in roles]
    # "<Tag> Wrangler" starts with the text, so it ranks above "Chief <Tag> Officer"
    assert titles == [f"{world['tag']} Wrangler", f"Chief {world['tag']} Officer"]
    assert all(r["openings"] == 1 for r in roles)


def test_suggests_hiring_managers_by_name(world):
    managers = suggest(world["tag"])["managers"]
    by_id = {m["id"]: m for m in managers}
    assert set(by_id) == {world["alpha"], world["gamma"]}   # beta's name doesn't match
    assert managers[0]["id"] == world["alpha"]              # first name starts with it: ranks first
    assert by_id[world["alpha"]]["open_roles"] == 1
    assert by_id[world["gamma"]]["open_roles"] == 0         # hiring, no job posted yet


def test_partial_word_matches(world):
    assert suggest(world["tag"][:4])["roles"]               # first few letters are enough
    assert any(r["title"] == "Night Baker" for r in suggest("ght bak")["roles"])


def test_wildcards_are_literal():
    assert suggest("%") == {"query": "%", "roles": [], "managers": []}
    assert suggest("_")["roles"] == [] and suggest("_")["managers"] == []


def test_suggest_limit_and_validation(world):
    assert len(suggest("e", limit=1)["roles"]) <= 1
    assert client.get("/search/suggest", params={"q": ""}).status_code == 422
    assert client.get("/search/suggest", params={"q": "a", "limit": 0}).status_code == 422
    assert client.get("/search/suggest", params={"q": "a", "limit": 11}).status_code == 422
    assert client.get("/search/suggest", params={"q": "  "}).json()["roles"] == []


# ---------------------------------------------------------------------------
# Searching roles and names together
# ---------------------------------------------------------------------------

def test_all_finds_name_and_role_matches_together(world):
    results = {r["target_id"]: r for r in search(world, world["tag"], search_type="all", limit=10)}
    assert set(results) == {world["alpha"], world["beta"], world["gamma"]}

    assert results[world["alpha"]]["match"] == ["role", "name"]   # name AND posted role match
    assert results[world["beta"]]["match"] == ["role"]            # only the role matches
    assert results[world["gamma"]]["match"] == ["name"]           # only the name matches

    # The matching job is shown, not just any job the manager has
    assert results[world["beta"]]["job"]["title"] == f"Chief {world['tag']} Officer"
    assert results[world["gamma"]]["job"] is None                 # no open job


def test_all_with_no_matches(world):
    assert search(world, "zz-no-such-thing-zz", search_type="all") == []
    assert search(world, "   ", search_type="all") == []


def test_role_and_manager_modes_report_what_matched(world):
    assert {r["match"][0] for r in search(world, world["tag"], search_type="role")} == {"role"}
    assert {r["match"][0] for r in search(world, world["tag"], search_type="manager")} == {"name"}


# ---------------------------------------------------------------------------
# Picking one person from the suggestions
# ---------------------------------------------------------------------------

def test_manager_id_searches_one_specific_person(world):
    results = search(world, "anything", manager_id=world["alpha"])
    assert [r["target_id"] for r in results] == [world["alpha"]]
    assert results[0]["path"] == [world["seeker"], world["alpha"]]
    assert results[0]["job"]["title"] == f"{world['tag']} Wrangler"


def test_manager_id_unknown_person(world):
    resp = client.get("/search", params={"seeker_id": world["seeker"], "q": "x", "manager_id": 999999999})
    assert resp.status_code == 404
