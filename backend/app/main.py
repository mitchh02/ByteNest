from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .routes import auth, connections, intros, search

app = FastAPI(title="GitConnectd API")

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
app.include_router(auth.router)
app.include_router(connections.router)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="frontend-assets")


@app.get("/", include_in_schema=False)
@app.get("/auth", include_in_schema=False)
def frontend():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/health")
def health():
    """Quick check that the server is running."""
    return {"ok": True}
