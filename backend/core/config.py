import os
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Maximum number of server-key analyses allowed per UTC day.
DEFAULT_DAILY_QUOTA: int = int(os.getenv("DEFAULT_DAILY_QUOTA") or "200")

# Bumped manually whenever the prompt or response schema changes so that
# old cached results are never served for a newer analysis version.
ANALYSIS_VERSION: str = "v1"

# ── CORS ──────────────────────────────────────────────────────────────────────
# Set CORS_ENV=production to restrict origins to the published extension only.
# Any other value (or omitted) is treated as development mode.
CORS_ENV: str = os.getenv("CORS_ENV", "development")

# The Chrome extension origin — fill in the real ID once published.
# Format: chrome-extension://<32-char-id>
EXTENSION_ID: str = os.getenv("EXTENSION_ID", "YOUR_EXTENSION_ID_HERE")

# ── Rate limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_ANALYZE: str = os.getenv("RATE_LIMIT_ANALYZE", "10/minute")


def validate_config() -> None:
    """Raise a clear error at startup if required env vars are missing."""
    missing = []
    if not YOUTUBE_API_KEY:
        missing.append("YOUTUBE_API_KEY")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Please set them in your .env file or environment before starting the server."
        )
