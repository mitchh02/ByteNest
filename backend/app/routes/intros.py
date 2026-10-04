"""
Intro requests: a warm introduction that travels down a path one person at a time.

Flow:
  1. The seeker picks a path from /search and sends a request (POST /intros).
     The first person on the path gets a message in their inbox.
  2. That person accepts or declines (POST /intros/{id}/respond).
     - Accept: the next person on the path gets a message.
     - Decline: the request stops. The seeker can search again for another path.
  3. When the hiring manager at the end accepts, the request is completed.
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db

router = APIRouter(tags=["intros"])


# ---------------------------------------------------------------------------
# Request bodies (FastAPI checks these automatically and returns 422 if wrong)
# ---------------------------------------------------------------------------

class NewIntro(BaseModel):
    seeker_id: int
    path: list[int]              # copied from a /search result: [seeker, ..., hiring manager]
    job_id: int | None = None
    pitch: str | None = None     # a short note from the seeker about themselves


class IntroResponse(BaseModel):
    user_id: int                 # who is answering
    accept: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connection(a, b):
    """The connection row between two people, or None. Pairs are stored smaller id first."""
    rows = db.query(
        "SELECT strength, context FROM user_connections WHERE user_a_id = %s AND user_b_id = %s",
        (min(a, b), max(a, b)),
    )
    return rows[0] if rows else None


def _names(user_ids):
    """{id: "First Last"} for the given people."""
    marks = ",".join(["%s"] * len(user_ids))
    rows = db.query(f"SELECT id, first_name, last_name FROM users WHERE id IN ({marks})", list(user_ids))
    return {r["id"]: f"{r['first_name']} {r['last_name']}" for r in rows}


def _goal(job_id):
    """A short description of what the seeker wants, for the message text."""
    if job_id:
        rows = db.query("SELECT title, company FROM job_openings WHERE id = %s", (job_id,))
        if rows:
            return f"a {rows[0]['title']} role at {rows[0]['company']}"
    return "a new role"


def _write_message(path, hop_index, goal, pitch):
    """
    Draft the message for one step of the path: from path[hop_index - 1] to path[hop_index].
    A plain template for now; an AI-written version can replace this later.
    """
    sender_id, receiver_id = path[hop_index - 1], path[hop_index]
    is_last = hop_index == len(path) - 1
    names = _names({path[0], sender_id, receiver_id} | ({path[hop_index + 1]} if not is_last else set()))
    seeker, sender, receiver = names[path[0]], names[sender_id], names[receiver_id]
    pitch_line = f' In their words: "{pitch}"' if pitch else ""

    if hop_index == 1:
        # First step: the seeker is writing for themselves
        ask = (f"Would you be open to introducing me to {names[path[2]]}?" if not is_last
               else "Would you be open to a quick chat?")
        return f"Hi {receiver}, I'm looking for {goal}. {ask} Thanks so much! - {seeker}"

    ask = (f"Would you be open to passing this along to {names[path[hop_index + 1]]}?" if not is_last
           else f"Would you be open to a quick chat with {seeker}?")
    return (f"Hi {receiver}, {seeker} is looking for {goal} and I thought you could help."
            f"{pitch_line} {ask} Thanks! - {sender}")


def _create_hop(request_id, path, hop_index, goal, pitch):
    """Store the message for one step, which puts it in that person's inbox."""
    db.execute(
        """INSERT INTO intro_hops (request_id, hop_index, from_user_id, to_user_id, message)
           VALUES (%s, %s, %s, %s, %s)""",
        (request_id, hop_index, path[hop_index - 1], path[hop_index],
         _write_message(path, hop_index, goal, pitch)),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/intros")
def create_intro(body: NewIntro):
    """Start a request down a path. The first person on the path gets the first message."""
    path = body.path

    # The path must start with the seeker, have at least one other person, and not repeat anyone
    if len(path) < 2 or path[0] != body.seeker_id:
        raise HTTPException(400, "Path must start with the seeker and include at least one other person")
    if len(set(path)) != len(path):
        raise HTTPException(400, "Path can't include the same person twice")

    # Every step must be a real connection, so nobody gets asked to forward to a stranger
    for a, b in zip(path, path[1:]):
        if _connection(a, b) is None:
            raise HTTPException(400, f"Users {a} and {b} aren't connected")

    request_id = db.execute(
        """INSERT INTO intro_requests (seeker_id, target_id, job_id, path_json, pitch)
           VALUES (%s, %s, %s, %s, %s)""",
        (body.seeker_id, path[-1], body.job_id, json.dumps(path), body.pitch),
    )
    _create_hop(request_id, path, 1, _goal(body.job_id), body.pitch)
    return get_intro(request_id)


@router.get("/intros/{request_id}")
def get_intro(request_id: int):
    """A request's status, its path, and every message sent so far (for tracking progress)."""
    rows = db.query("SELECT * FROM intro_requests WHERE id = %s", (request_id,))
    if not rows:
        raise HTTPException(404, "Request not found")
    request = rows[0]
    request["path"] = json.loads(request.pop("path_json"))
    request["hops"] = db.query(
        "SELECT * FROM intro_hops WHERE request_id = %s ORDER BY hop_index", (request_id,)
    )
    return request


@router.get("/inbox/{user_id}")
def inbox(user_id: int):
    """Messages waiting for this person to accept or decline."""
    return db.query(
        """SELECT h.id, h.request_id, h.hop_index, h.from_user_id, h.message,
                  r.seeker_id, r.target_id, r.job_id
           FROM intro_hops h JOIN intro_requests r ON r.id = h.request_id
           WHERE h.to_user_id = %s AND h.status = 'pending' AND r.status = 'pending'
           ORDER BY h.id DESC""",
        (user_id,),
    )


@router.post("/intros/{request_id}/respond")
def respond(request_id: int, body: IntroResponse):
    """The person whose turn it is accepts (forward it on) or declines (stop here)."""
    request = get_intro(request_id)
    if request["status"] != "pending":
        raise HTTPException(409, f"This request is already {request['status']}")

    path, hop_index = request["path"], request["current_hop"]
    if path[hop_index] != body.user_id:
        raise HTTPException(403, "It's not this person's turn to respond")

    # Record this person's answer
    db.execute(
        """UPDATE intro_hops SET status = %s, responded_at = NOW()
           WHERE request_id = %s AND hop_index = %s""",
        ("accepted" if body.accept else "declined", request_id, hop_index),
    )

    if not body.accept:
        db.execute("UPDATE intro_requests SET status = 'declined' WHERE id = %s", (request_id,))
    elif hop_index == len(path) - 1:
        # The hiring manager accepted: the intro made it all the way
        db.execute("UPDATE intro_requests SET status = 'completed' WHERE id = %s", (request_id,))
    else:
        # Move to the next person and put a message in their inbox
        db.execute("UPDATE intro_requests SET current_hop = %s WHERE id = %s", (hop_index + 1, request_id))
        _create_hop(request_id, path, hop_index + 1, _goal(request["job_id"]), request["pitch"])

    return get_intro(request_id)
