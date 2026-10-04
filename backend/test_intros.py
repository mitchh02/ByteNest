"""
Tests for the intro request endpoints (app/routes/intros.py).

Run from the backend folder, with MariaDB running and test data loaded:
    pip install pytest httpx
    python -m pytest test_intros.py -v

These call the API the same way the frontend will, using your real database.
Any intro requests they create are deleted afterwards.
"""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Setup: find a real path to test with, and clean up afterwards
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def path_info():
    """Find a seeker with at least one path of 2+ hops to a hiring manager."""
    try:
        seekers = [r["id"] for r in db.query("SELECT id FROM users ORDER BY id LIMIT 30")]
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")

    for seeker in seekers:
        # An empty search matches every open job
        results = client.get("/search", params={"seeker_id": seeker, "q": ""}).json()["results"]
        for r in results:
            if r["hops"] >= 2:
                return {"seeker": seeker, "path": r["path"], "job_id": r["job"]["id"]}
    pytest.skip("no seeker with a 2+ hop path; run the seed script first")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    """Delete every intro request created by these tests (their hops are deleted with them)."""
    created = []
    yield created
    for request_id in created:
        db.execute("DELETE FROM intro_requests WHERE id = %s", (request_id,))


def start_intro(path_info, cleanup):
    """Send a new intro request down the test path and remember it for cleanup."""
    resp = client.post("/intros", json={
        "seeker_id": path_info["seeker"],
        "path": path_info["path"],
        "job_id": path_info["job_id"],
        "pitch": "Test pitch",
    })
    assert resp.status_code == 200, resp.text
    request = resp.json()
    cleanup.append(request["id"])
    return request


def respond(request_id, user_id, accept):
    return client.post(f"/intros/{request_id}/respond", json={"user_id": user_id, "accept": accept})


def inbox_has(user_id, request_id):
    return any(item["request_id"] == request_id for item in client.get(f"/inbox/{user_id}").json())


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_request_travels_down_the_path_to_completion(path_info, cleanup):
    path = path_info["path"]
    request = start_intro(path_info, cleanup)

    # A new request starts pending, waiting on the first person after the seeker
    assert request["status"] == "pending"
    assert request["current_hop"] == 1
    assert request["path"] == path
    assert len(request["hops"]) == 1
    assert request["hops"][0]["from_user_id"] == path[0]
    assert request["hops"][0]["to_user_id"] == path[1]

    # Each person in turn sees the message in their inbox, then accepts
    for i in range(1, len(path)):
        assert inbox_has(path[i], request["id"]), f"message missing from inbox of person {i}"
        resp = respond(request["id"], path[i], accept=True)
        assert resp.status_code == 200, resp.text
        request = resp.json()

        # Their message is now marked accepted and gone from their inbox
        assert request["hops"][i - 1]["status"] == "accepted"
        assert not inbox_has(path[i], request["id"])

        if i < len(path) - 1:
            # Not the end yet: the next person gets a message
            assert request["status"] == "pending"
            assert request["current_hop"] == i + 1
            assert request["hops"][i]["to_user_id"] == path[i + 1]

    # The hiring manager accepted, so the intro made it all the way
    assert request["status"] == "completed"
    assert len(request["hops"]) == len(path) - 1


def test_messages_mention_the_people_involved(path_info, cleanup):
    request = start_intro(path_info, cleanup)
    first = request["hops"][0]["message"]
    names = {r["id"]: r["first_name"] for r in db.query(
        "SELECT id, first_name FROM users WHERE id IN (%s, %s)", (path_info["path"][0], path_info["path"][1]))}
    assert names[path_info["path"][1]] in first   # addressed to the receiver
    assert names[path_info["path"][0]] in first   # signed by the seeker


# ---------------------------------------------------------------------------
# Declines and turn-taking
# ---------------------------------------------------------------------------

def test_decline_stops_the_request(path_info, cleanup):
    path = path_info["path"]
    request = start_intro(path_info, cleanup)

    resp = respond(request["id"], path[1], accept=False)
    assert resp.status_code == 200
    request = resp.json()
    assert request["status"] == "declined"
    assert request["hops"][0]["status"] == "declined"
    assert len(request["hops"]) == 1               # nobody further was messaged
    assert not inbox_has(path[2], request["id"])


def test_only_the_current_person_can_respond(path_info, cleanup):
    path = path_info["path"]
    request = start_intro(path_info, cleanup)

    assert respond(request["id"], path[-1], accept=True).status_code == 403   # hiring manager, too early
    assert respond(request["id"], path[0], accept=True).status_code == 403    # the seeker
    assert respond(request["id"], path[1], accept=True).status_code == 200    # the right person


def test_cannot_respond_after_finished(path_info, cleanup):
    path = path_info["path"]
    request = start_intro(path_info, cleanup)
    respond(request["id"], path[1], accept=False)

    assert respond(request["id"], path[1], accept=True).status_code == 409


# ---------------------------------------------------------------------------
# Bad input
# ---------------------------------------------------------------------------

def test_path_must_start_with_the_seeker(path_info):
    path = path_info["path"]
    resp = client.post("/intros", json={"seeker_id": path_info["seeker"], "path": path[1:]})
    assert resp.status_code == 400


def test_path_needs_at_least_two_people(path_info):
    resp = client.post("/intros", json={"seeker_id": path_info["seeker"], "path": [path_info["seeker"]]})
    assert resp.status_code == 400


def test_path_cannot_repeat_a_person(path_info):
    s, p1 = path_info["path"][0], path_info["path"][1]
    resp = client.post("/intros", json={"seeker_id": s, "path": [s, p1, s]})
    assert resp.status_code == 400


def test_every_step_must_be_a_real_connection(path_info):
    seeker = path_info["seeker"]
    stranger = db.query(
        """SELECT id FROM users WHERE id != %s AND id NOT IN (
               SELECT IF(user_a_id = %s, user_b_id, user_a_id) FROM user_connections
               WHERE %s IN (user_a_id, user_b_id))
           LIMIT 1""",
        (seeker, seeker, seeker),
    )[0]["id"]
    resp = client.post("/intros", json={"seeker_id": seeker, "path": [seeker, stranger]})
    assert resp.status_code == 400


def test_missing_fields_are_rejected():
    assert client.post("/intros", json={"path": [1, 2]}).status_code == 422   # no seeker_id


def test_unknown_request_is_404():
    assert client.get("/intros/999999999").status_code == 404
    assert respond(999999999, 1, accept=True).status_code == 404
