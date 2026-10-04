from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import intros, search

app = FastAPI(title="Six Degrees Hiring API")

# Let the frontend (running on a different port) call this API from the browser.
# "*" allows any site, which is fine for a hackathon but should be locked down later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(intros.router)

@app.get("/health")
def health():
    """Quick check that the server is running."""
    return {"ok": True}