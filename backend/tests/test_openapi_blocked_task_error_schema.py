# ruff: noqa: INP001, S101

from __future__ import annotations

from app.main import app


def test_openapi_blocked_task_error_includes_code_field() -> None:
    schema = app.openapi()

    blocked_detail = schema["components"]["schemas"]["BlockedTaskDetail"]
    props = blocked_detail.get("properties", {})

    # `code` is optional but must be documented for clients.
    assert "code" in props
    required_fields = blocked_detail.get("required", [])
    assert "code" not in required_fields

    code_schema = props["code"]
    any_of = code_schema.get("anyOf")
    assert isinstance(any_of, list) and any_of

    has_string_branch = any(branch.get("type") == "string" for branch in any_of)
    assert has_string_branch

    has_null_branch = any(branch.get("type") == "null" or branch.get("nullable") is True for branch in any_of)
    assert has_null_branch
