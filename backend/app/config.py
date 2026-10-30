"""All limits come from environment variables so they can be tuned without code changes."""
import os
from pathlib import Path

MB = 1024 * 1024
BACKEND = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


DATA_DIR = Path(os.environ.get("DATA_DIR", BACKEND / "data"))
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", BACKEND.parent / "frontend" / "dist"))

MAX_FILE_BYTES = _int("MAX_FILE_MB", 50) * MB
MAX_TOTAL_BYTES = _int("MAX_TOTAL_MB", 200) * MB
MAX_FILES = _int("MAX_FILES", 20)

JOB_TTL_SECONDS = _int("JOB_TTL_MINUTES", 60) * 60
JOB_TIMEOUT_SECONDS = _int("JOB_TIMEOUT_SECONDS", 300)
JOB_MEMORY_BYTES = _int("JOB_MEMORY_MB", 4096) * MB
JOB_MAX_OUTPUT_BYTES = _int("JOB_MAX_OUTPUT_MB", 1024) * MB
MAX_CONCURRENT_JOBS = _int("MAX_CONCURRENT_JOBS", 2)
MAX_QUEUED_JOBS = _int("MAX_QUEUED_JOBS", 50)

# Read inside the sandbox too (passed through by sandbox.py).
MAX_PAGES = _int("MAX_PAGES", 2000)
MAX_RENDER_DPI = _int("MAX_RENDER_DPI", 300)
MAX_RENDER_PAGES = _int("MAX_RENDER_PAGES", 500)   # PDF to images/slides
MAX_IMAGE_PIXELS = _int("MAX_IMAGE_PIXELS", 100_000_000)
MAX_UNZIPPED_BYTES = _int("MAX_UNZIPPED_MB", 500) * MB
MAX_ZIP_ENTRIES = _int("MAX_ZIP_ENTRIES", 2000)
MAX_ZIP_RATIO = _int("MAX_ZIP_RATIO", 100)
SANDBOX_ENV = ("MAX_PAGES", "MAX_RENDER_DPI", "MAX_RENDER_PAGES", "MAX_IMAGE_PIXELS", "MAX_UNZIPPED_MB",
               "MAX_ZIP_ENTRIES", "MAX_ZIP_RATIO", "DEBUG_JOBS", "AI_MAX_CHARS")

# Optional AI tools: sends extracted text to the Claude API. Off by default.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_ENABLED = os.environ.get("AI_ENABLED", "").lower() == "true" and bool(ANTHROPIC_API_KEY)
AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")
AI_MAX_CHARS = _int("AI_MAX_CHARS", 400_000)   # roughly 100k tokens

RATE_LIMIT = os.environ.get("RATE_LIMIT", "30/minute")
ALLOWED_ORIGINS = set(os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:5173").split(","))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
DEBUG_JOBS = os.environ.get("DEBUG_JOBS") == "1"  # show sandbox stderr; never enable in production
