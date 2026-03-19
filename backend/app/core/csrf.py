"""Lightweight CSRF protection for local auth mode using double-submit pattern."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status

from app.core.auth_mode import AuthMode
from app.core.config import settings

if TYPE_CHECKING:
    from starlette.responses import Response

CSRF_COOKIE_NAME = "mc_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """Set the CSRF cookie on a response."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,  # JS needs to read it for double-submit
        samesite="strict",
        secure=False,  # Local auth is typically non-TLS
        max_age=86400,
    )


def verify_csrf(request: Request) -> None:
    """Verify CSRF token for mutating requests in local auth mode."""
    if settings.auth_mode != AuthMode.LOCAL:
        return
    if request.method.upper() in SAFE_METHODS:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_token or not header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing",
        )
    if not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token mismatch",
        )
