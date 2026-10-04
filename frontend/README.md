# Frontend

FastAPI serves this browser frontend at `/` and `/auth`, with CSS and JavaScript
under `/assets`. It calls the API on the same origin. No Node installation or
frontend build is required.

From the repository root, with backend dependencies installed and the database
configured in `.env`:

```bash
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Open http://localhost:8000/. Search the demo network using a seeded user ID, or
sign in to search as yourself and request introductions. To give a seeded user
a password:

```bash
python backend/set_password.py 1 demo1234
```

The script prints their login email. New accounts start without connections.
To choose a starting profile by name, enter a first, last, or full name and click
**Find user**. Choose a matching profile from the list; company, title, location,
and ID help distinguish people with the same name. You can also switch **Start
from** to **User ID**. Signed-in users search from their own profile automatically.
Choose **Hiring manager name** in the search selector to find a person by first,
last, or full name. Matching hiring managers can appear even without an open
job posting. **Job role** searches open job titles and descriptions as before.
Introduction requests and the inbox require the `intro_requests` and `intro_hops`
database tables used by the backend.

The earlier React components in `src/` remain available as source; the served
frontend lives in this directory.
