import pytest
from pydantic import ValidationError

from schemas.relevance import (
    BulkLabelPayload,
    FewShotExportQuery,
    HumanLabelPayload,
    PromptEvalPayload,
    PromptRollbackPayload,
    ReclassifyBulkPayload,
    RelevanceMetricsQuery,
    RelevanceQueueQuery,
)


def test_queue_query_clamps_and_falls_back_to_default_mode():
    q = RelevanceQueueQuery.from_request_args({"mode": "bogus", "page": "-5", "per_page": "9999"})
    assert q.mode == "uncertainty"
    assert q.page == 1
    assert q.per_page == 100


def test_queue_query_accepts_known_modes():
    for mode in ("uncertainty", "audit", "failed", "labeled", "disagreement", "all"):
        assert RelevanceQueueQuery.from_request_args({"mode": mode}).mode == mode


def test_human_label_payload_falls_back_invalid_label_source():
    p = HumanLabelPayload.from_body({"is_relevant": True, "label_source": "nonsense"})
    assert p.label_source == "targeted"


def test_human_label_payload_accepts_audit_source():
    p = HumanLabelPayload.from_body({"is_relevant": False, "label_source": "audit"})
    assert p.label_source == "audit"


def test_bulk_label_drops_non_numeric_ids_and_caps_at_50():
    ids = [str(i) for i in range(60)] + ["abc"]
    p = BulkLabelPayload.from_body({"berita_ids": ids, "is_relevant": False})
    assert len(p.berita_ids) == 50
    assert all(isinstance(i, int) for i in p.berita_ids)


def test_reclassify_bulk_caps_ids_and_limit():
    p = ReclassifyBulkPayload.from_body({"berita_ids": list(range(100)), "limit": "999"})
    assert len(p.berita_ids) == 25
    assert p.limit == 25


def test_prompt_rollback_rejects_bad_version_pattern():
    """WAJIB raise -- Flask menangkapnya lewat errorhandler(ValidationError) di
    app.py yang mengubahnya jadi 400 bersih, bukan 500."""
    with pytest.raises(ValidationError):
        PromptRollbackPayload.from_body({"version": "not-a-version", "confirmation": "x"})


def test_prompt_rollback_accepts_valid_version_pattern():
    p = PromptRollbackPayload.from_body({"version": "rel-v7", "confirmation": "x"})
    assert p.version == "rel-v7"


def test_prompt_eval_rejects_short_draft():
    with pytest.raises(ValidationError):
        PromptEvalPayload.from_body({"draft_prompt": "too short"})


def test_prompt_eval_accepts_valid_draft_and_clamps_sample_size():
    long_draft = "x" * 250
    p = PromptEvalPayload.from_body({"draft_prompt": long_draft, "sample_size": "999"})
    assert p.sample_size == 60


def test_metrics_query_allows_none_prompt_version():
    q = RelevanceMetricsQuery.from_request_args({})
    assert q.prompt_version is None


def test_few_shot_export_query_clamps_below_minimum():
    q = FewShotExportQuery.from_request_args({"limit": "1"})
    assert q.limit == 5
