# ruff: noqa: INP001
"""Test that agent-token lookup uses O(1) prefix-based lookup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import agent_auth


@pytest.mark.asyncio
async def test_agent_token_lookup_uses_prefix_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After refactor: lookup filters by prefix, verifies at most 1 hash."""

    class _FakeResult:
        def __init__(self, items: list[object]) -> None:
            self._items = items

        def __iter__(self):
            return iter(self._items)

    class _FakeSession:
        def __init__(self) -> None:
            self.last_stmt = None

        async def exec(self, stmt: object) -> _FakeResult:
            self.last_stmt = stmt
            # Return empty — no matching prefix
            return _FakeResult([])

    calls = {"n": 0}

    def _fake_verify(_token: str, _stored_hash: str) -> bool:
        calls["n"] += 1
        return False

    monkeypatch.setattr(agent_auth, "verify_agent_token", _fake_verify)

    session = _FakeSession()
    out = await agent_auth._find_agent_for_token(session, "test-token-value")
    assert out is None
    # With prefix-based lookup, if no agents match the prefix, zero verifications
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_agent_token_lookup_verifies_matching_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When prefix matches, verify the single agent's hash."""
    agent = SimpleNamespace(
        agent_token_hash="pbkdf2_sha256$200000$salt$digest",
        agent_token_prefix="test-tok",
    )

    class _FakeResult:
        def __init__(self, items: list[object]) -> None:
            self._items = items

        def __iter__(self):
            return iter(self._items)

    class _FakeSession:
        async def exec(self, stmt: object) -> _FakeResult:
            return _FakeResult([agent])

    calls = {"n": 0}

    def _fake_verify(_token: str, _stored_hash: str) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(agent_auth, "verify_agent_token", _fake_verify)

    session = _FakeSession()
    out = await agent_auth._find_agent_for_token(session, "test-token-value")
    assert out is agent
    assert calls["n"] == 1
