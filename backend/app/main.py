import logging
import os
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_db
from .routers import auth, jobs, resumes, analyze


def _configure_logging() -> None:
    """Console + rotating file logging.

    File goes to data/app.log so it sits alongside the SQLite DB and is
    already covered by the .gitignore on backend/data/.
    Rotation keeps the file from growing forever during demos.
    """
    log_dir = "./data"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    # uvicorn --reload re-imports this module on every code change, so wipe
    # any existing handlers first to avoid duplicate lines per event.
    root.handlers.clear()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)

    # Chromadb spams "telemetry capture()" errors at us thanks to a posthog
    # version mismatch. They're harmless, just hide them.
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


_configure_logging()
logger = logging.getLogger("resume-analyzer")

app = FastAPI(title="AI Resume Analyzer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized")
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set. Embeddings/LLM calls will fail.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "error": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok", "gemini_configured": bool(settings.GEMINI_API_KEY)}


app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(resumes.router)
app.include_router(analyze.router)
