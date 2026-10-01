"""Environment configuration. Secrets are read from .env and never given defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    gemini_api_key: str | None
    gemini_model: str | None
    resend_api_key: str | None
    email_from: str
    demo_mode: bool
    demo_recipient: str | None
    dashboard_username: str
    dashboard_password: str | None

    def missing(self) -> list[str]:
        missing = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if not self.gemini_model:
            missing.append("GEMINI_MODEL")
        if not self.resend_api_key:
            missing.append("RESEND_API_KEY")
        if self.demo_mode and not self.demo_recipient:
            missing.append("DEMO_RECIPIENT")
        return missing


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL") or None,
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        gemini_model=os.environ.get("GEMINI_MODEL") or None,
        resend_api_key=os.environ.get("RESEND_API_KEY") or None,
        email_from=os.environ.get("EMAIL_FROM", "Kargo Hiring <onboarding@resend.dev>"),
        demo_mode=os.environ.get("DEMO_MODE", "true").strip().lower() != "false",
        demo_recipient=os.environ.get("DEMO_RECIPIENT") or None,
        dashboard_username=os.environ.get("DASHBOARD_USERNAME", "arjun"),
        # Unset = local, unauthenticated use (CLAUDE.md's original v1 spec).
        # Set = every route requires this password (HTTP Basic). Only meant
        # to be set when this app is reachable from outside localhost.
        dashboard_password=os.environ.get("DASHBOARD_PASSWORD") or None,
    )


settings = load_settings()
