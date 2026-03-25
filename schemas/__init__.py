"""Schema validasi input API."""

from schemas.admin import CreateUserPayload, CreateUsersPayload
from schemas.auth import ChangePasswordPayload, LoginPayload, ResetPasswordPayload
from schemas.berita import BeritaFilterQuery
from schemas.scraping import ScrapeTriggerPayload

__all__ = [
    "BeritaFilterQuery",
    "LoginPayload",
    "ChangePasswordPayload",
    "ResetPasswordPayload",
    "CreateUserPayload",
    "CreateUsersPayload",
    "ScrapeTriggerPayload",
]
