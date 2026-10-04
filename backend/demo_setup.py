"""
Set up demo accounts for walking an introduction down a path, live.

Finds a strong 2-3 hop path from a job seeker to a hiring manager, gives
everyone on it a readable email and the same password, clears any old
introductions between them, and prints a step-by-step demo script.

Run from the backend folder:
    python demo_setup.py                         # pick the best path automatically
    python demo_setup.py --role "Backend"        # path to someone hiring for this role
    python demo_setup.py --seeker 12             # start from a specific user
    python demo_setup.py --password demo1234 --hops 2-3

Safe to run again: it only touches the people on the chosen path. If you load
a different dataset, just run it again.
"""
import argparse
import re

from app import db, graph
from app.security import hash_password


def parse_hops(text):
    low, _, high = text.partition("-")
    return int(low), int(high or low)


def open_jobs(role):
    """Open jobs, optionally only those whose title matches `role`."""
    if role:
        return db.query("SELECT id, title, company, posted_by FROM job_openings "
                        "WHERE is_open AND title LIKE %s ORDER BY id", (f"%{role}%",))
    return db.query("SELECT id, title, company, posted_by FROM job_openings WHERE is_open ORDER BY id")


def candidate_seekers(limit=150):
    """People who aren't hiring and know at least two others: good demo job seekers."""
    return [r["id"] for r in db.query(
        """SELECT u.id FROM users u
           JOIN user_connections c ON u.id IN (c.user_a_id, c.user_b_id)
           WHERE NOT u.is_hiring
             AND NOT EXISTS (SELECT 1 FROM job_openings j WHERE j.posted_by = u.id AND j.is_open)
           GROUP BY u.id HAVING COUNT(*) >= 2
           ORDER BY COUNT(*) DESC, u.id LIMIT %s""", (limit,))]


def best_path(seekers, jobs, min_hops, max_hops):
    """The strongest path with min_hops..max_hops introductions from any seeker to any job's poster."""
    managers = list(dict.fromkeys(j["posted_by"] for j in jobs))
    best = None
    for seeker in seekers:
        for r in graph.best_paths(seeker, managers, limit=len(managers)):
            if min_hops <= r["hops"] <= max_hops and (best is None or r["score"] > best["score"]):
                best = r
    return best


def readable_email(person, taken_by_others):
    """first.last@demo.dev, with a number added if someone else already has it."""
    base = re.sub(r"[^a-z0-9.]", "", f"{person['first_name']}.{person['last_name']}".lower()) or "user"
    email, n = f"{base}@demo.dev", 2
    while email in taken_by_others:
        email, n = f"{base}{n}@demo.dev", n + 1
    return email


def set_up_account(person, password):
    """Give one person a readable login email (also their contact email) and the demo password."""
    uid = person["id"]
    taken = {r["email"] for r in db.query("SELECT email FROM users WHERE id != %s", (uid,))}
    taken |= {r["value"] for r in db.query(
        "SELECT value FROM user_contacts WHERE contact_type = 'email' AND user_id != %s", (uid,))}
    email = readable_email(person, taken)
    with db.transaction() as cur:
        # Their old login email is also stored as a contact; swap it for the new one
        cur.execute("DELETE FROM user_contacts WHERE user_id = %s AND contact_type = 'email' AND value = "
                    "(SELECT email FROM users WHERE id = %s)", (uid, uid))
        cur.execute("UPDATE users SET email = %s, password_hash = %s WHERE id = %s",
                    (email, hash_password(password), uid))
        cur.execute("INSERT IGNORE INTO user_contacts (user_id, contact_type, value, is_public) "
                    "VALUES (%s, 'email', %s, FALSE)", (uid, email))
    return email


def clear_intros(user_ids):
    """Delete introduction requests started by, or travelling through, these people."""
    marks = ",".join(["%s"] * len(user_ids))
    ids = [r["id"] for r in db.query(
        f"""SELECT DISTINCT r.id FROM intro_requests r
            LEFT JOIN intro_hops h ON h.request_id = r.id
            WHERE r.seeker_id IN ({marks}) OR r.target_id IN ({marks}) OR h.to_user_id IN ({marks})""",
        user_ids * 3)]
    for request_id in ids:
        db.execute("DELETE FROM intro_requests WHERE id = %s", (request_id,))   # hops go with it
    return len(ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeker", type=int, help="user id of the job seeker (default: pick automatically)")
    parser.add_argument("--role", help="only paths to someone hiring for a role containing this text")
    parser.add_argument("--hops", default="2-3", help="introductions in the path, e.g. 2-3 (default) or 2")
    parser.add_argument("--password", default="demo1234", help="password for every demo account")
    args = parser.parse_args()

    min_hops, max_hops = parse_hops(args.hops)
    if len(args.password) < 6:
        parser.error("password must be at least 6 characters")

    jobs = open_jobs(args.role)
    if not jobs:
        parser.error(f"no open jobs{' matching ' + repr(args.role) if args.role else ''}")
    seekers = [args.seeker] if args.seeker else candidate_seekers()
    if not seekers:
        parser.error("no users with at least two connections; load some data first")

    print("Finding the strongest demo path…")
    path = best_path(seekers, jobs, min_hops, max_hops)
    if not path:
        parser.error(f"no path with {args.hops} introductions found; try --hops 1-4 or a different --role")

    job = next(j for j in jobs if j["posted_by"] == path["target_id"])
    people = path["people"]
    accounts = [(p, set_up_account(p, args.password)) for p in people]
    cleared = clear_intros([p["id"] for p in people])

    # --- The demo script ---
    name = lambda p: f"{p['first_name']} {p['last_name']}"
    print(f"\nDemo path: {path['hops']} introductions, {round(path['score'] * 100)}% path strength")
    print(f"Job: {job['title']} at {job['company']}\n")
    print(f"{'':<4}{'Name':<24}{'Role in the demo':<28}{'Email':<34}Password")
    for i, (p, email) in enumerate(accounts):
        role = "Job seeker (you)" if i == 0 else "Hiring manager" if i == len(accounts) - 1 else f"Connection {i}"
        print(f"{i + 1:<4}{name(p):<24}{role:<28}{email:<34}{args.password}")
    print("\nHow each pair knows each other:")
    for i, reason in enumerate(path["reasons"]):
        print(f"  {name(people[i])} → {name(people[i + 1])}: {reason or 'connected'}")
    if cleared:
        print(f"\nCleared {cleared} old introduction request(s) involving these people.")

    print("\nDemo steps (use a normal window and a private window, so two people can be signed in):")
    print(f"  1. Sign in as {name(people[0])} ({accounts[0][1]}).")
    print(f"  2. Search \"{job['title']}\" and click Request introduction on the path to {name(people[-1])}.")
    for i in range(1, len(people)):
        last = i == len(people) - 1
        print(f"  {i + 2}. In the other window, sign in as {name(people[i])} ({accounts[i][1]}) and click "
              f"Accept introduction{' — the hiring manager says yes!' if last else '.'}")
    print(f"\nTo set this path up again from scratch later: python demo_setup.py --seeker {people[0]['id']}"
          f"{' --role ' + repr(args.role) if args.role else ''} --hops {args.hops}")


if __name__ == "__main__":
    main()
