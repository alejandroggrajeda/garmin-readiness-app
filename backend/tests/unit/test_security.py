"""Unit tests for `app.api.security.require_api_key` — the static
`X-API-Key` guard (design.md: "Single-user: no accounts, one static
`X-API-Key`."). Pure dependency-function tests, no DB, no ASGI client.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.security import require_api_key
from app.config import get_settings


def test_correct_key_is_accepted() -> None:
    require_api_key(x_api_key=get_settings().api_key)  # must not raise


def test_missing_key_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key=None)
    assert exc_info.value.status_code == 401


def test_wrong_key_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key="definitely-not-it")
    assert exc_info.value.status_code == 401
