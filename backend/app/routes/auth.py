"""
Sign up, sign in, and "who am I?" endpoints, backed by the MariaDB users table.

The frontend flow:
  1. POST /auth/signup or /auth/login  ->  {"token": "...", "user": {...}}
  2. Save the token (localStorage) and send it on later requests as
     the header "Authorization: Bearer <token>".
  3. GET /auth/me with that header to find out who is signed in.

Sign-up needs only a name, email and password. Everything else (profile, phone,
GitHub, an open role for hiring managers) is optional and saved in the same
step. All of it is saved together or not at all, so a duplicate phone number
can't leave a half-created account behind.
"""
import re

import pymysql
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..security import USER_COLUMNS, current_user, hash_password, make_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# GitHub usernames: letters, digits and single hyphens, not starting or ending
# with a hyphen, at most 39 characters
GITHUB_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


class SignUp(BaseModel):
    # Required
    email: str
    password: str
    first_name: str
    last_name: str
    # Optional profile
    job_title: str | None = None
    company: str | None = None
    location: str | None = None
    bio: str | None = None
    # Optional contact details (saved to user_contacts, each unique across users)
    phone: str | None = None
    github: str | None = None
    # Hiring managers can post one open role while signing up
    is_hiring: bool = False
    open_role: str | None = None


class SignIn(BaseModel):
    email: str
    password: str


# ---------------------------------------------------------------------------
# Cleaning and checking input
# ---------------------------------------------------------------------------

def _clean_email(email):
    email = email.strip().lower()
    # A light check; the frontend validates the format more carefully
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 255:
        raise HTTPException(400, "Enter a valid email")
    return email


def _optional(value, label, max_length):
    """Trim an optional text field; empty becomes None. Rejects text that's too long."""
    if value is None:
        return None
    value = " ".join(value.split()) if label != "Bio" else value.strip()
    if not value:
        return None
    if len(value) > max_length:
        raise HTTPException(400, f"{label} must be {max_length} characters or fewer")
    return value


def _clean_phone(phone):
    """
    Keep only the digits, so "+1 (555) 123-4567" and "1 555 123 4567" are stored
    the same way and the uniqueness rule treats them as the same number.
    """
    if phone is None or not phone.strip():
        return None
    if not re.fullmatch(r"\+?[0-9 ().\-]+", phone.strip()):
        raise HTTPException(400, "Enter a valid phone number")
    digits = re.sub(r"\D", "", phone)
    if not 7 <= len(digits) <= 15:   # 15 is the international maximum
        raise HTTPException(400, "Enter a valid phone number")
    # A 10-digit number written without "+" is treated as US/Canada, so
    # "555 123 4567" and "+1 555 123 4567" count as the same number
    if len(digits) == 10 and not phone.strip().startswith("+"):
        digits = "1" + digits
    return digits


def _clean_github(github):
    """GitHub usernames ignore case, so store them lowercase. Accepts a leading @."""
    if github is None or not github.strip():
        return None
    github = github.strip().removeprefix("@")
    if not GITHUB_RE.fullmatch(github):
        raise HTTPException(400, "Enter a valid GitHub username")
    return github.lower()


def _contact_taken(contact_type, value):
    return bool(db.query(
        "SELECT 1 FROM user_contacts WHERE contact_type = %s AND value = %s", (contact_type, value)))


def _signed_in(user_id):
    """The response the frontend gets after signing up or in."""
    user = db.query(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,))[0]
    return {"token": make_token(user_id), "user": user}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/signup", status_code=201)
def signup(body: SignUp):
    # --- Required fields ---
    email = _clean_email(body.email)
    first = _optional(body.first_name, "First name", 100)
    last = _optional(body.last_name, "Last name", 100)
    if not first or not last:
        raise HTTPException(400, "Enter your first and last name")
    # 72 matches the frontend's limit; 6 is the minimum it enforces
    if not 6 <= len(body.password) <= 72:
        raise HTTPException(400, "Password must be 6 to 72 characters")

    # --- Optional fields ---
    job_title = _optional(body.job_title, "Job title", 150)
    company = _optional(body.company, "Company", 150)
    location = _optional(body.location, "Location", 150)
    bio = _optional(body.bio, "Bio", 1000)
    phone = _clean_phone(body.phone)
    github = _clean_github(body.github)
    open_role = _optional(body.open_role, "Open role", 150) if body.is_hiring else None
    if open_role and not company:
        raise HTTPException(400, "Enter your company to post an open role")

    # --- Nothing may already belong to someone else ---
    if db.query("SELECT id FROM users WHERE email = %s", (email,)):
        raise HTTPException(409, "An account with this email already exists")
    if _contact_taken("email", email):
        raise HTTPException(409, "This email is already registered to another user")
    if phone and _contact_taken("phone", phone):
        raise HTTPException(409, "This phone number is already registered to another user")
    if github and _contact_taken("github", github):
        raise HTTPException(409, "This GitHub account is already registered to another user")

    # --- Save everything together ---
    try:
        with db.transaction() as cur:
            cur.execute(
                """INSERT INTO users (first_name, last_name, email, password_hash,
                                      job_title, company, location, bio, is_hiring)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (first, last, email, hash_password(body.password),
                 job_title, company, location, bio, body.is_hiring),
            )
            user_id = cur.lastrowid

            # Contacts: email and phone stay private; a GitHub profile is public
            contacts = [("email", email, False)]
            if phone:
                contacts.append(("phone", phone, False))
            if github:
                contacts.append(("github", github, True))
            cur.executemany(
                "INSERT INTO user_contacts (user_id, contact_type, value, is_public) VALUES (%s, %s, %s, %s)",
                [(user_id, kind, value, public) for kind, value, public in contacts],
            )

            if open_role:
                cur.execute(
                    "INSERT INTO job_openings (posted_by, title, company, description) VALUES (%s, %s, %s, %s)",
                    (user_id, open_role, company, f"{company} is hiring a {open_role}."),
                )
    except pymysql.err.IntegrityError as exc:
        # Someone took the same email, phone or GitHub between our check and the save
        if exc.args and exc.args[0] == 1062:
            raise HTTPException(409, "That email, phone number or GitHub account was just registered by someone else")
        raise

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
