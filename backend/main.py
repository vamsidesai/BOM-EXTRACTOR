"""BOMX FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes import dashboard, drawings, export, extract, upload, viewer
from .seed import seed_sample_drawings
from .storage import ensure_storage_dirs, PREVIEWS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bomx.api")

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_dirs()
    # Seed samples in background thread so server starts promptly
    import threading
    t = threading.Thread(target=seed_sample_drawings, daemon=True)
    t.start()
    log.info("BOMX REST API started successfully.")
    yield


app = FastAPI(
    title="BOMX - Drawing BOM & Material Extractor API",
    version="2.0.0",
    description="Enterprise REST API for engineering drawing analysis, OCR extraction, and BOM review.",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(upload.router)
app.include_router(extract.router)
app.include_router(drawings.router)
app.include_router(viewer.router)
app.include_router(export.router)
app.include_router(dashboard.router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "bomx-api",
        "version": "2.0.0",
    }


# Mount Static Assets & Single Page Application (SPA)
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return None
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8501, reload=True)
