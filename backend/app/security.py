"""
Password hashing and login tokens, using only Python's standard library.

Passwords: never stored as typed. We store a salted PBKDF2 hash, so even someone
who reads the database can't recover the password.

Tokens: after login, the browser gets a token like "42.1759600000.<signature>".
It says "user 42, valid until this time", and the signature proves our server
issued it. Changing any part of it breaks the signature, so it can't be forged
without the secret key.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Header, HTTPException

from . import db

PBKDF2_ITERATIONS = 600_000         # how much work each hash takes; slows down guessing
TOKEN_LIFETIME = 7 * 24 * 3600      # tokens expire after 7 days

# The key used to sign tokens. Set AUTH_SECRET in .env to a long random string.
SECRET = os.getenv("AUTH_SECRET")
if not SECRET:
    print("WARNING: AUTH_SECRET is not set in .env; using an insecure development key.")
    SECRET = "dev-only-insecure-key-change-me"


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(password):
    """Turn a password into 'pbkdf2_sha256$iterations$salt$hash' for storage."""
    salt = secrets.token_bytes(16)   # random per user, so identical passwords hash differently
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password, stored):
    """True if the password matches the stored hash."""
    if not stored:
        return False                 # seeded users with no password can't log in
    try:
        algorithm, iterations, salt_b64, hash_b64 = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
    # compare_digest takes the same time whether the first or last byte differs,
    # so attackers can't learn anything from how long the check takes
    return hmac.compare_digest(digest, base64.b64decode(hash_b64))


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def _sign(message):
    return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


def make_token(user_id):
    """A signed token saying which user this is and when it expires."""
    message = f"{user_id}.{int(time.time()) + TOKEN_LIFETIME}"
    return f"{message}.{_sign(message)}"


def read_token(token):
    """The user id inside a valid, unexpired token, or None."""
    try:
        user_id, expires, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(f"{user_id}.{expires}")):
            return None              # forged or tampered with
        if int(expires) < time.time():
            return None              # expired
        return int(user_id)
    except (ValueError, AttributeError):
        return None                  # not even shaped like a token


# ---------------------------------------------------------------------------
# For endpoints that need a logged-in user
# ---------------------------------------------------------------------------

USER_COLUMNS = "id, first_name, last_name, email, job_title, company, bio, location, is_hiring"


def current_user(authorization: str | None = Header(default=None)):
    """
    Use as `user: dict = Depends(current_user)` in an endpoint. Reads the
    "Authorization: Bearer <token>" header and returns that user, or responds 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not signed in")
    user_id = read_token(authorization.removeprefix("Bearer "))
    if user_id is None:
        raise HTTPException(401, "Session expired or invalid; please sign in again")
    rows = db.query(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,))
    if not rows:
        raise HTTPException(401, "Account no longer exists")
    return rows[0]
