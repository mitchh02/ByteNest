"""
The signed-in user's own connections: the people they know.

A new account starts with no connections, so its searches find nothing. These
endpoints let a user add the people they know and say how well they know them,
which is what the path search runs on.

Closeness (1-5) becomes the connection's strength (0.2-1.0):
    1 = met once      -> 0.2
    2 = acquaintance  -> 0.4
    3 = know them     -> 0.6
    4 = worked together -> 0.8
    5 = close         -> 1.0

All endpoints need the "Authorization: Bearer <token>" header.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db
from ..security import current_user

router = APIRouter(prefix="/me/connections", tags=["connections"])


class NewConnection(BaseModel):
    user_id: int                                  # the person you know
    closeness: int = Field(ge=1, le=5)            # 1 (met once) to 5 (close)
    context: str | None = Field(default=None, max_length=255)   # "Worked together at Acme"


def _strength(closeness):
    return round(closeness / 5, 2)


def _list(user_id):
    """Everyone this user is connected to, strongest first."""
    rows = db.query(
        """SELECT u.id, u.first_name, u.last_name, u.job_title, u.company, u.location,
                  c.strength, c.source, c.context
           FROM user_connections c
           JOIN users u ON u.id = IF(c.user_a_id = %s, c.user_b_id, c.user_a_id)
           WHERE %s IN (c.user_a_id, c.user_b_id)
           ORDER BY c.strength DESC, u.first_name, u.last_name""",
        (user_id, user_id),
    )
    for r in rows:
        r["strength"] = float(r["strength"])
        r["closeness"] = max(1, min(5, round(r["strength"] * 5)))   # back to the 1-5 scale
    return rows


@router.get("")
def list_connections(user: dict = Depends(current_user)):
    return _list(user["id"])


@router.post("", status_code=201)
def add_connection(body: NewConnection, user: dict = Depends(current_user)):
    """Add someone you know, or update how well you know them if already connected."""
    if body.user_id == user["id"]:
        raise HTTPException(400, "You can't add yourself as a connection")
    if not db.query("SELECT 1 FROM users WHERE id = %s", (body.user_id,)):
        raise HTTPException(404, "That person doesn't exist")

    context = " ".join(body.context.split()) if body.context else None
    a, b = sorted((user["id"], body.user_id))   # pairs are stored smaller id first
    db.execute(
        """INSERT INTO user_connections (user_a_id, user_b_id, strength, source, context)
           VALUES (%s, %s, %s, 'self_rated', %s)
           ON DUPLICATE KEY UPDATE strength = VALUES(strength),
                                   source = VALUES(source),
                                   context = COALESCE(VALUES(context), context)""",
        (a, b, _strength(body.closeness), context),
    )
    return next(c for c in _list(user["id"]) if c["id"] == body.user_id)


@router.delete("/{other_id}", status_code=204)
def remove_connection(other_id: int, user: dict = Depends(current_user)):
    a, b = sorted((user["id"], other_id))
    db.execute("DELETE FROM user_connections WHERE user_a_id = %s AND user_b_id = %s", (a, b))
