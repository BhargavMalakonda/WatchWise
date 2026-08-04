from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.config import validate_config
from core.security import get_cors_origins, limiter
from routes.analyze import router as analyze_router

# Validate required environment variables before the app starts accepting requests
validate_config()

app = FastAPI(
    title="WatchWise API",
    description="Analyses YouTube videos for educational value, outdated content, and misinformation risk.",
    version="0.1.0",
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET","POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ----------Render (health endpoints) ------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "WatchWise API",
        "version": "0.1.0"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

app.include_router(analyze_router, prefix="/api/v1")
