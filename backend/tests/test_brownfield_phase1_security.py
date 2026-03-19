# ruff: noqa: INP001
"""Tests for Phase 1 and Phase 2 brownfield security fixes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.agent_tokens import (
    TOKEN_PREFIX_LENGTH,
    generate_agent_token,
    hash_agent_token,
    token_prefix,
    verify_agent_token,
)
from app.core.encryption import decrypt_value, encrypt_value


# --- 1. Token prefix tests ---


def test_token_prefix_length() -> None:
    """token_prefix returns exactly TOKEN_PREFIX_LENGTH chars."""
    token = generate_agent_token()
    prefix = token_prefix(token)
    assert len(prefix) == TOKEN_PREFIX_LENGTH
    assert token.startswith(prefix)


def test_token_prefix_consistency() -> None:
    """Same token always produces the same prefix."""
    token = generate_agent_token()
    assert token_prefix(token) == token_prefix(token)


def test_different_tokens_likely_different_prefixes() -> None:
    """Different tokens should (almost always) have different prefixes."""
    tokens = [generate_agent_token() for _ in range(20)]
    prefixes = {token_prefix(t) for t in tokens}
    # With 8-char prefixes from urlsafe_b64, collision among 20 is near-impossible
    assert len(prefixes) == 20


def test_hash_and_verify_roundtrip() -> None:
    """hash_agent_token + verify_agent_token roundtrip works."""
    token = generate_agent_token()
    hashed = hash_agent_token(token)
    assert verify_agent_token(token, hashed)
    assert not verify_agent_token("wrong-token", hashed)


# --- 2. Gateway token encryption tests ---


def test_encrypt_decrypt_roundtrip() -> None:
    """encrypt_value + decrypt_value roundtrip preserves plaintext."""
    plaintext = "my-secret-gateway-token-12345"
    ciphertext = encrypt_value(plaintext)
    assert ciphertext != plaintext
    assert decrypt_value(ciphertext) == plaintext


def test_encrypt_produces_different_ciphertexts() -> None:
    """Fernet uses nonce, so same plaintext produces different ciphertexts."""
    plaintext = "same-token"
    c1 = encrypt_value(plaintext)
    c2 = encrypt_value(plaintext)
    # Fernet includes timestamp + nonce, so results differ
    assert c1 != c2
    # Both decrypt to same value
    assert decrypt_value(c1) == plaintext
    assert decrypt_value(c2) == plaintext


def test_decrypt_invalid_ciphertext_raises() -> None:
    """decrypt_value raises on invalid/tampered ciphertext."""
    with pytest.raises(Exception):
        decrypt_value("not-valid-fernet-token")


def test_gateway_model_encrypt_decrypt() -> None:
    """Gateway.set_encrypted_token / get_decrypted_token integration."""
    from app.models.gateways import Gateway

    gw = Gateway(
        organization_id=uuid4(),
        name="test-gw",
        url="https://gw.example.com",
        workspace_root="/workspace",
    )
    assert gw.get_decrypted_token() is None

    gw.set_encrypted_token("secret-token")
    assert gw.encrypted_token is not None
    assert gw.token is None  # plaintext cleared
    assert gw.get_decrypted_token() == "secret-token"

    gw.set_encrypted_token(None)
    assert gw.encrypted_token is None
    assert gw.get_decrypted_token() is None


def test_gateway_model_fallback_to_plaintext() -> None:
    """get_decrypted_token falls back to plaintext token when encrypted_token is None."""
    from app.models.gateways import Gateway

    gw = Gateway(
        organization_id=uuid4(),
        name="test-gw",
        url="https://gw.example.com",
        workspace_root="/workspace",
        token="legacy-plaintext-token",
    )
    assert gw.encrypted_token is None
    assert gw.get_decrypted_token() == "legacy-plaintext-token"


# --- 3. Security headers config defaults ---


def test_security_headers_have_defaults() -> None:
    """Config defaults should have security headers enabled."""
    from app.core.config import Settings

    # Settings() reads env — our test conftest sets AUTH_MODE=local etc.
    # Just verify the class defaults are non-empty.
    defaults = Settings.model_fields
    assert defaults["security_header_x_content_type_options"].default == "nosniff"
    assert defaults["security_header_x_frame_options"].default == "DENY"
    assert defaults["security_header_referrer_policy"].default == "strict-origin-when-cross-origin"
    assert "camera=()" in defaults["security_header_permissions_policy"].default


# --- 4. Pagination cap ---


def test_pagination_cap_at_100() -> None:
    """Verify pagination schema file caps limit at 100."""
    import re
    from pathlib import Path

    pagination_file = Path(__file__).resolve().parents[1] / "app" / "schemas" / "pagination.py"
    content = pagination_file.read_text()
    # Verify le=100 constraint is present
    assert "le=100" in content
    # Verify default is 100
    match = re.search(r"limit=Query\((\d+),", content)
    assert match is not None
    assert match.group(1) == "100"


# --- 5. CSRF token generation ---


def test_csrf_token_generation() -> None:
    """generate_csrf_token returns unique tokens."""
    from app.core.csrf import generate_csrf_token

    t1 = generate_csrf_token()
    t2 = generate_csrf_token()
    assert t1 != t2
    assert len(t1) > 20


# --- 6. Rate limiter exists ---


def test_rate_limiter_configured() -> None:
    """Rate limiter should be importable and configured."""
    from app.core.rate_limit import limiter

    assert limiter is not None


# --- 7. db_agent_state sets prefix ---


def test_mint_agent_token_sets_prefix() -> None:
    """mint_agent_token should set both hash and prefix on the agent."""
    from app.services.openclaw.db_agent_state import mint_agent_token

    agent = SimpleNamespace(agent_token_hash=None, agent_token_prefix=None)
    raw_token = mint_agent_token(agent)

    assert agent.agent_token_hash is not None
    assert agent.agent_token_prefix is not None
    assert len(agent.agent_token_prefix) == TOKEN_PREFIX_LENGTH
    assert raw_token.startswith(agent.agent_token_prefix)
    assert verify_agent_token(raw_token, agent.agent_token_hash)
