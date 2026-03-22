"""
Schema payload autentikasi.
"""

from typing import Any, Mapping

from pydantic import BaseModel, Field


class LoginPayload(BaseModel):
    """Payload login dari endpoint /api/login."""

    username: str = Field(default="")
    password: str = Field(default="")

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "LoginPayload":
        payload = {
            "username": str(body.get("username", "")).strip().lower()[:100],
            "password": str(body.get("password", "")).strip()[:200],
        }
        return cls.model_validate(payload)


class ChangePasswordPayload(BaseModel):
    """Payload ganti password untuk user yang sedang login."""

    new_password: str = Field(default="")

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "ChangePasswordPayload":
        payload = {"new_password": str(body.get("new_password", "")).strip()}
        return cls.model_validate(payload)


class ResetPasswordPayload(BaseModel):
    """Payload reset password berbasis kode autentikasi."""

    username: str = Field(default="")
    code: str = Field(default="")
    new_password: str = Field(default="")

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "ResetPasswordPayload":
        payload = {
            "username": str(body.get("username", "")).strip().lower()[:100],
            "code": str(body.get("code", "")).strip().upper()[:8],
            "new_password": str(body.get("new_password", "")).strip(),
        }
        return cls.model_validate(payload)
