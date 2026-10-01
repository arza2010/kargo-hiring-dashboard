"""HTTP Basic auth gate, applied to every route in app/main.py.

CLAUDE.md's original v1 spec was local-only with no auth, on the assumption
nothing but 127.0.0.1 could ever reach this app. Once it's deployed
somewhere reachable from outside localhost, that assumption breaks: this app
holds candidate PII and a working Send button. So: if DASHBOARD_PASSWORD is
set, every request must authenticate. If it's unset (the default for local
dev), behavior is unchanged from the original spec.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

_security = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(_security)) -> None:
    if not settings.dashboard_password:
        return  # no password configured — unauthenticated local use, unchanged

    unauthorized = HTTPException(
        status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"}
    )
    if credentials is None:
        raise unauthorized

    user_ok = secrets.compare_digest(credentials.username, settings.dashboard_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not (user_ok and pass_ok):
        raise unauthorized
