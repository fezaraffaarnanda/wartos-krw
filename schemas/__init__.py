"""Schema validasi input API."""

from schemas.admin import CreateUserPayload, CreateUsersPayload
from schemas.auth import ChangePasswordPayload, LoginPayload, ResetPasswordPayload
from schemas.berita import BeritaFilterQuery
from schemas.feedback import ActivityTrackPayload, FeedbackListQuery, FeedbackSubmitPayload
from schemas.relevance import (
    AuditSamplePayload,
    BulkLabelPayload,
    FewShotExportQuery,
    HumanLabelPayload,
    PromptApplyPayload,
    PromptDraftPayload,
    PromptEvalPayload,
    PromptRollbackPayload,
    ReclassifyBulkPayload,
    RelevanceMetricsQuery,
    RelevanceQueueQuery,
)
from schemas.scraping import NewsSourceOut, ScrapeTriggerPayload

__all__ = [
    "BeritaFilterQuery",
    "LoginPayload",
    "ChangePasswordPayload",
    "ResetPasswordPayload",
    "CreateUserPayload",
    "CreateUsersPayload",
    "ScrapeTriggerPayload",
    "NewsSourceOut",
    "RelevanceQueueQuery",
    "HumanLabelPayload",
    "BulkLabelPayload",
    "ReclassifyBulkPayload",
    "AuditSamplePayload",
    "PromptDraftPayload",
    "PromptEvalPayload",
    "PromptApplyPayload",
    "PromptRollbackPayload",
    "FewShotExportQuery",
    "RelevanceMetricsQuery",
    "ActivityTrackPayload",
    "FeedbackSubmitPayload",
    "FeedbackListQuery",
]
