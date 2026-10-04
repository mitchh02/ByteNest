"""
Sign up, sign in, and "who am I?" endpoints, backed by the MariaDB users table.

The frontend flow:
  1. POST /auth/signup or /auth/login  ->  {"token": "...", "user": {...}}
  2. Save the token (localStorage) and send it on later requests as
     the header "Authorization: Bearer <token>".
  3. GET /auth/me with that header to find out who is signed in.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..security import USER_COLUMNS, current_user, hash_password, make_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class SignUp(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str


class SignIn(BaseModel):
    email: str
    password: str


def _clean_email(email):
    email = email.strip().lower()
    # A light check; the frontend validates the format more carefully
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 255:
        raise HTTPException(400, "Enter a valid email")
    return email


def _signed_in(user_id):
    """The response the frontend gets after signing up or in."""
    user = db.query(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,))[0]
    return {"token": make_token(user_id), "user": user}


@router.post("/signup", status_code=201)
def signup(body: SignUp):
    email = _clean_email(body.email)
    first, last = body.first_name.strip(), body.last_name.strip()
    if not first or not last:
        raise HTTPException(400, "Enter your first and last name")
    # 72 matches the frontend's limit; 6 is the minimum it enforces
    if not 6 <= len(body.password) <= 72:
        raise HTTPException(400, "Password must be 6 to 72 characters")

    # The email must not belong to anyone, as a login or as another user's contact
    if db.query("SELECT id FROM users WHERE email = %s", (email,)):
        raise HTTPException(409, "An account with this email already exists")
    if db.query("SELECT id FROM user_contacts WHERE contact_type = 'email' AND value = %s", (email,)):
        raise HTTPException(409, "This email is already registered to another user")

    user_id = db.execute(
        """INSERT INTO users (first_name, last_name, email, password_hash)
           VALUES (%s, %s, %s, %s)""",
        (first, last, email, hash_password(body.password)),
    )
    # Also record the login email as a contact, so the uniqueness rule covers it
    db.execute(
        "INSERT INTO user_contacts (user_id, contact_type, value, is_public) VALUES (%s, 'email', %s, FALSE)",
        (user_id, email),
    )
    return _signed_in(user_id)


@router.post("/login")
def login(body: SignIn):
    email = body.email.strip().lower()
    rows = db.query("SELECT id, password_hash FROM users WHERE email = %s", (email,))
    # Same message whether the email or the password is wrong, so the form
    # doesn't reveal which emails have accounts
    if not rows or not verify_password(body.password, rows[0]["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    return _signed_in(rows[0]["id"])


@router.get("/me")
def me(user: dict = Depends(current_user)):
    """The signed-in user (requires the Authorization header)."""
    return user
