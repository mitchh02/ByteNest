from fastapi import APIRouter, HTTPException
from typing import Literal

from .. import db, graph

# A router groups related endpoints; main.py plugs it into the app
router = APIRouter(tags=["search"])


@router.get("/search")
def search(seeker_id: int, q: str, limit: int = 3,
           search_type: Literal["role", "manager"] = "role"):
    """
    Search by role (default), or by a hiring manager's first, last, or full name.
    Manager searches include hiring users without an open job posting.
    """
    # Make sure the seeker exists, so a typo gives a clear error instead of empty results
    if not db.query("SELECT id FROM users WHERE id = %s", (seeker_id,)):
        raise HTTPException(status_code=404, detail="Seeker not found")

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
    for r in results:
        r["job"] = job_by_manager.get(r["target_id"])

    return {"query": q, "results": results}
