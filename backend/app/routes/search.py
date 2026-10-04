from fastapi import APIRouter, HTTPException

from .. import db, graph

# A router groups related endpoints; main.py plugs it into the app
router = APIRouter(tags=["search"])


@router.get("/search")
def search(seeker_id: int, q: str, limit: int = 3):
    """
    Find open jobs matching q, then the strongest path from the seeker to each
    job's hiring manager. Example: /search?seeker_id=1&q=engineer
    """
    # Make sure the seeker exists, so a typo gives a clear error instead of empty results
    if not db.query("SELECT id FROM users WHERE id = %s", (seeker_id,)):
        raise HTTPException(status_code=404, detail="Seeker not found")

    # Find matching open jobs. LIKE with %...% matches the words anywhere in the text,
    # and the collation makes it case-insensitive ("Engineer" matches "engineer").
    pattern = f"%{q}%"
    jobs = db.query(
        """SELECT id, title, company, posted_by FROM job_openings
           WHERE is_open AND (title LIKE %s OR description LIKE %s)""",
        (pattern, pattern),
    )
    if not jobs:
        return {"query": q, "results": []}

    # One hiring manager may post several matching jobs; keep the first for each
    job_by_manager = {}
    for job in jobs:
        job_by_manager.setdefault(job["posted_by"], job)

    # Find the strongest paths to those hiring managers (graph.py does the real work)
    results = graph.best_paths(seeker_id, list(job_by_manager), limit=limit)

    # Attach the job each path leads to, so the frontend can show it
    for r in results:
        r["job"] = job_by_manager[r["target_id"]]

    return {"query": q, "results": results}
