"""Central configuration, read once from environment variables (or backend/.env).

Nothing secret is hard-coded here. All secrets live in environment variables.
"""
import logging
import os
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# Local development: load backend/.env if it exists. On Render the real
# environment variables are used instead (load_dotenv never overrides them).
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("careertrack.config")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.environment = os.getenv("ENVIRONMENT", "development").strip().lower()
        self.demo_mode = _env_bool("DEMO_MODE", False)
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip()
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        self.supabase_publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        self.frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip().rstrip("/")
        self.api_key = os.getenv("BACKEND_API_KEY", "").strip()
        self.timezone = os.getenv("APP_TIMEZONE", "UTC").strip() or "UTC"
        self.allow_demo_seed = _env_bool("ALLOW_DEMO_SEED", self.demo_mode)
        self.demo_db_path = os.getenv("DEMO_DB_PATH", str(BASE_DIR / "demo.db"))

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origins(self) -> List[str]:
        """Production: ONLY the configured frontend. Development: also localhost."""
        origins = [self.frontend_origin] if self.frontend_origin else []
        if not self.is_production:
            origins += ["http://localhost:8501", "http://127.0.0.1:8501"]
        return origins


settings = Settings()


def validate_settings() -> None:
    """Fail fast with a readable message if the configuration is unusable."""
    problems: List[str] = []

    if settings.is_production and settings.demo_mode:
        problems.append("DEMO_MODE must be false when ENVIRONMENT=production.")
    if settings.is_production and not settings.api_key:
        problems.append("BACKEND_API_KEY is required when ENVIRONMENT=production.")
    if not settings.demo_mode:
        if not settings.supabase_url:
            problems.append("SUPABASE_URL is missing (or set DEMO_MODE=true to try the app locally).")
        if not settings.supabase_service_key:
            problems.append("SUPABASE_SERVICE_KEY is missing (or set DEMO_MODE=true).")
    try:
        ZoneInfo(settings.timezone)
    except Exception:
        problems.append(f"APP_TIMEZONE '{settings.timezone}' is not a valid time zone name.")

    if problems:
        raise RuntimeError("Configuration problems:\n- " + "\n- ".join(problems))

    if settings.is_production and not settings.frontend_origin:
        logger.warning("FRONTEND_ORIGIN is not set: browsers from other origins will be blocked by CORS.")
    if not settings.gemini_api_key and not settings.demo_mode:
        logger.warning("GEMINI_API_KEY is not set: AI endpoints will return a 503 error.")
