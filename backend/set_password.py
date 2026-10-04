"""
Give an existing user a password, so you can sign in as them.

Seeded test users have no password (they can't log in), and a brand-new account
has no connections to search through. Use this to sign in as a seeded user
for the demo.

    python set_password.py 1 demo1234                 # by user id
    python set_password.py maya@example.com demo1234  # by email

It prints the email to sign in with.
"""
import sys

from app import db
from app.security import hash_password

if len(sys.argv) != 3:
    sys.exit(__doc__)

who, password = sys.argv[1], sys.argv[2]
if len(password) < 6:
    sys.exit("Password must be at least 6 characters (the sign-in form requires it).")

column = "id" if who.isdigit() else "email"
rows = db.query(f"SELECT id, email, first_name, last_name FROM users WHERE {column} = %s", (who,))
if not rows:
    sys.exit(f"No user with {column} {who}")

user = rows[0]
db.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(password), user["id"]))
print(f"Password set for {user['first_name']} {user['last_name']} (id {user['id']}).")
print(f"Sign in with: {user['email']} / {password}")
