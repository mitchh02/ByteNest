from fastapi import APIRouter, HTTPException, Query
from typing import Literal

from .. import db, graph

# A router groups related endpoints; main.py plugs it into the app
router = APIRouter(tags=["search"])

# SQL that counts open jobs for a user, and says whether they're a hiring manager
_OPEN_ROLES = "(SELECT COUNT(*) FROM job_openings j WHERE j.posted_by = u.id AND j.is_open)"
_IS_MANAGER = f"(u.is_hiring OR {_OPEN_ROLES} > 0)"
_FULL_NAME = "CONCAT_WS(' ', u.first_name, u.last_name)"


def _escape_like(text):
    """Treat LIKE wildcards (% and _) as literal characters; '!' is the escape character."""
    return text.replace('!', '!!').replace('%', '!%').replace('_', '!_')


def _patterns(text):
    """
    Three LIKE patterns used to rank matches, best first:
      starts  - the whole text starts with it         ("Eng" -> "Engineering Manager")
      word    - some word starts with it              ("eng" -> "Backend Engineer")
      contains - it appears anywhere                   ("gine" -> "Backend Engineer")
    """
    safe = _escape_like(text)
    return {"starts": f"{safe}%", "word": f"% {safe}%", "contains": f"%{safe}%"}


@router.get("/users/lookup")
def lookup_users(q: str = Query(min_length=1, max_length=201)):
    """Find public profiles by name, keeping duplicate names selectable by ID."""
    name = " ".join(q.split())
    if not name:
        return {"users": []}
    pattern = '%' + name.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
    users = db.query(
        """SELECT id, first_name, last_name, job_title, company, location FROM users
           WHERE CONCAT_WS(' ', first_name, last_name) LIKE %s ESCAPE '!'
           ORDER BY first_name, last_name, id LIMIT 25""", (pattern,))
    return {"users": users}


@router.get("/search/suggest")
def suggest(q: str = Query(min_length=1, max_length=201), limit: int = Query(6, ge=1, le=10)):
    """
    Suggestions while the user types: open job roles and hiring managers whose
    names match, best matches first. Fast enough to call on every keystroke.
    """
    text = " ".join(q.split())
    if not text:
        return {"query": q, "roles": [], "managers": []}
    p = _patterns(text)

    # Distinct open job titles, with how many openings each has
    roles = db.query(
        """SELECT title, COUNT(*) AS openings FROM job_openings
           WHERE is_open AND title LIKE %(contains)s ESCAPE '!'
           GROUP BY title
           ORDER BY CASE WHEN title LIKE %(starts)s ESCAPE '!' THEN 0
                         WHEN CONCAT(' ', title) LIKE %(word)s ESCAPE '!' THEN 1
                         ELSE 2 END,
                    openings DESC, title
           LIMIT %(limit)s""",
        {**p, "limit": limit},
    )

    # Hiring managers (hiring, or with an open job) whose names match
    managers = db.query(
        f"""SELECT u.id, u.first_name, u.last_name, u.job_title, u.company,
                   {_OPEN_ROLES} AS open_roles
            FROM users u
            WHERE {_FULL_NAME} LIKE %(contains)s ESCAPE '!' AND {_IS_MANAGER}
            ORDER BY CASE WHEN {_FULL_NAME} LIKE %(starts)s ESCAPE '!' THEN 0
                          WHEN CONCAT(' ', {_FULL_NAME}) LIKE %(word)s ESCAPE '!' THEN 1
                          ELSE 2 END,
                     u.first_name, u.last_name, u.id
            LIMIT %(limit)s""",
        {**p, "limit": limit},
    )
    for m in managers:
        m["open_roles"] = int(m["open_roles"])
    return {"query": q, "roles": roles, "managers": managers}


@router.get("/search")
def search(seeker_id: int, q: str, limit: int = 3,
           search_type: Literal["role", "manager", "all"] = "role",
           manager_id: int | None = None):
    """
    Search by role (default), by a hiring manager's first, last, or full name,
    or both at once ("all"). Manager searches include hiring users without an
    open job posting. manager_id searches for one specific person, e.g. after
    picking them from the suggestions.

    Each result has "match": what the query matched, ["role"], ["name"] or both.
    """
    # Make sure the seeker exists, so a typo gives a clear error instead of empty results
    if not db.query("SELECT id FROM users WHERE id = %s", (seeker_id,)):
        raise HTTPException(status_code=404, detail="Seeker not found")

    if manager_id is not None:
        return _search_one_manager(seeker_id, q, manager_id)
    if search_type == "all":
        return _search_all(seeker_id, q, limit)

    if search_type == "manager":
        name = " ".join(q.split())
        if not name:
            return {"query": q, "results": []}
        # Treat LIKE wildcards as literal name characters; values stay parameterized.
        pattern = '%' + name.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        managers = db.query(
            """SELECT u.id FROM users u
               WHERE CONCAT_WS(' ', u.first_name, u.last_name) LIKE %s ESCAPE '!'
                 AND (u.is_hiring OR EXISTS (
                     SELECT 1 FROM job_openings j WHERE j.posted_by = u.id AND j.is_open))
               ORDER BY u.id""", (pattern,))
        target_ids = [manager["id"] for manager in managers]
        if not target_ids:
            return {"query": q, "results": []}
        marks = ','.join(['%s'] * len(target_ids))
        jobs = db.query(
            f"""SELECT id, title, company, posted_by FROM job_openings
                WHERE is_open AND posted_by IN ({marks}) ORDER BY id""", target_ids)
    else:
        pattern = f"%{q}%"
        jobs = db.query(
            """SELECT id, title, company, posted_by FROM job_openings
               WHERE is_open AND (title LIKE %s OR description LIKE %s) ORDER BY id""",
            (pattern, pattern),
        )
        target_ids = list(dict.fromkeys(job["posted_by"] for job in jobs))
        if not target_ids:
            return {"query": q, "results": []}

    # One hiring manager may post several matching jobs; keep the first for each
    job_by_manager = {}
    for job in jobs:
        job_by_manager.setdefault(job["posted_by"], job)

    # Find the strongest paths to those hiring managers (graph.py does the real work)
    results = graph.best_paths(seeker_id, target_ids, limit=limit)

    # Attach the job each path leads to, so the frontend can show it
    match = ["name"] if search_type == "manager" else ["role"]
    for r in results:
        r["job"] = job_by_manager.get(r["target_id"])
        r["match"] = match

    return {"query": q, "results": results}


def _open_jobs_by(manager_ids):
    """{manager id: their first open job} for the given managers."""
    if not manager_ids:
        return {}
    marks = ','.join(['%s'] * len(manager_ids))
    jobs = db.query(
        f"""SELECT id, title, company, posted_by FROM job_openings
            WHERE is_open AND posted_by IN ({marks}) ORDER BY id""", list(manager_ids))
    first = {}
    for job in jobs:
        first.setdefault(job["posted_by"], job)
    return first


def _search_all(seeker_id, q, limit):
    """Hiring managers whose name matches OR who posted a matching role, ranked together."""
    text = " ".join(q.split())
    if not text:
        return {"query": q, "results": []}
    contains = _patterns(text)["contains"]

    # Managers whose name matches
    named = [m["id"] for m in db.query(
        f"""SELECT u.id FROM users u
            WHERE {_FULL_NAME} LIKE %s ESCAPE '!' AND {_IS_MANAGER} ORDER BY u.id""", (contains,))]

    # Open jobs whose title or description matches
    role_jobs = db.query(
        """SELECT id, title, company, posted_by FROM job_openings
           WHERE is_open AND (title LIKE %s ESCAPE '!' OR description LIKE %s ESCAPE '!')
           ORDER BY id""", (contains, contains))

    # Prefer the matching job for each manager; otherwise show any open job they have
    job_by_manager = {}
    for job in role_jobs:
        job_by_manager.setdefault(job["posted_by"], job)
    role_managers = set(job_by_manager)
    for manager, job in _open_jobs_by([m for m in named if m not in job_by_manager]).items():
        job_by_manager[manager] = job

    target_ids = list(dict.fromkeys([*named, *(j["posted_by"] for j in role_jobs)]))
    if not target_ids:
        return {"query": q, "results": []}

    results = graph.best_paths(seeker_id, target_ids, limit=limit)
    named_set = set(named)
    for r in results:
        r["job"] = job_by_manager.get(r["target_id"])
        r["match"] = [kind for kind, hit in (("role", r["target_id"] in role_managers),
                                             ("name", r["target_id"] in named_set)) if hit]
    return {"query": q, "results": results}


def _search_one_manager(seeker_id, q, manager_id):
    """The strongest path to one specific person (picked from the suggestions)."""
    if not db.query("SELECT id FROM users WHERE id = %s", (manager_id,)):
        raise HTTPException(status_code=404, detail="That person doesn't exist")
    results = graph.best_paths(seeker_id, [manager_id], limit=1)
    job = _open_jobs_by([manager_id]).get(manager_id)
    for r in results:
        r["job"] = job
        r["match"] = ["name"]
    return {"query": q, "results": results}
