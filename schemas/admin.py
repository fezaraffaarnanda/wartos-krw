"""
Schema payload admin.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

_USERNAME_SPLIT_PATTERN = re.compile(r"[\s,]+")


def _normalize_username(value: Any) -> str:
    return str(value or "").strip().lower()[:50]


def _extract_usernames(body: Mapping[str, Any]) -> list[str]:
    raw_usernames = body.get("usernames")
    tokens: list[str] = []

    if isinstance(raw_usernames, str):
        tokens.extend(_USERNAME_SPLIT_PATTERN.split(raw_usernames))
    elif isinstance(raw_usernames, Sequence):
        for item in raw_usernames:
            if isinstance(item, str):
                tokens.extend(_USERNAME_SPLIT_PATTERN.split(item))
            else:
                tokens.append(str(item))
    elif raw_usernames is not None:
        tokens.append(str(raw_usernames))

    if not tokens and "username" in body:
        tokens.extend(_USERNAME_SPLIT_PATTERN.split(str(body.get("username", ""))))

    normalized: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        username = _normalize_username(token)
        if not username or username in seen:
            continue
        seen.add(username)
        normalized.append(username)

    return normalized


class CreateUsersPayload(BaseModel):
    """Payload pembuatan user oleh admin."""

    usernames: list[str] = Field(default_factory=list)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "CreateUsersPayload":
        return cls.model_validate({"usernames": _extract_usernames(body)})


CreateUserPayload = CreateUsersPayload
