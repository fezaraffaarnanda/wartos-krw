from services.relevance_feedback_service import (
    RelevanceFeedbackService,
    _band_for_score,
    _confusion_block,
    _metrics_by_version,
    _weighted_confusion_block,
)


class _FakeBeritaRepo:
    """Row audit dikenali dari kolom `label_source`, sama seperti di DB.

    `audit_rows` masih diterima demi tes lama, tapi isinya digabung ke satu
    daftar: service hanya boleh menarik confusion rows sekali."""

    def __init__(self, confusion_rows=None, audit_rows=None, band_population=None):
        self._confusion_rows = list(confusion_rows or [])
        for row in audit_rows or []:
            if row not in self._confusion_rows:
                self._confusion_rows.append(row)
        self._band_population = band_population or {}
        self.confusion_calls = 0

    def relevance_confusion_rows(self, *, label_source=None, prompt_version=None):
        self.confusion_calls += 1
        if label_source == "audit":
            return [r for r in self._confusion_rows if r.get("label_source") == "audit"]
        return self._confusion_rows

    def count_scored_by_band(self):
        return self._band_population


def test_band_for_score_boundaries():
    assert _band_for_score(0) == "b00_19"
    assert _band_for_score(19) == "b00_19"
    assert _band_for_score(20) == "b20_39"
    assert _band_for_score(59) == "b40_59"
    assert _band_for_score(60) == "b60_79"
    assert _band_for_score(100) == "b80_100"
    assert _band_for_score(None) is None


def test_f1_is_zero_not_none_when_precision_and_recall_are_zero():
    """Defect lama: `if precision and recall` mengubah precision=recall=0.0
    (classifier terburuk, tp=0) jadi f1=None ('-' di UI). Percobaan perbaikan
    pertama (`(p+r) > 0`) masih gagal di kasus SAMA PERSIS ini, karena
    precision=0 selalu membuat recall=0 juga (tp dibagi di kedua rumus).
    Konvensi standar (scikit-learn dkk): F1=0.0 untuk classifier terburuk."""
    rows = [
        {"is_relevant": True, "human_label": False},   # fp
        {"is_relevant": False, "human_label": True},   # fn
    ]
    block = _confusion_block(rows)
    assert block["precision"] == 0.0
    assert block["recall"] == 0.0
    assert block["f1"] == 0.0


def test_f1_stays_none_when_denominator_genuinely_undefined():
    block = _confusion_block([])
    assert block["precision"] is None
    assert block["recall"] is None
    assert block["f1"] is None
    assert block["accuracy"] is None


def test_confusion_block_counts_all_four_quadrants():
    rows = [
        {"is_relevant": True, "human_label": True},
        {"is_relevant": True, "human_label": False},
        {"is_relevant": False, "human_label": False},
        {"is_relevant": False, "human_label": True},
    ]
    block = _confusion_block(rows)
    assert block["confusion"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert block["labeled_count"] == 4
    assert block["precision"] == 0.5
    assert block["recall"] == 0.5
    assert block["accuracy"] == 0.5
    assert round(block["f1"], 4) == 0.5


def test_weighted_confusion_uses_band_population_not_raw_count():
    """Sampel audit 2 baris di band yang populasinya 100 -> tiap baris mewakili
    50 baris populasi. Ini yang membuat sampel kecil bisa mengestimasi korpus."""
    rows = [
        {"is_relevant": True, "human_label": True, "relevance_score": 10},
        {"is_relevant": False, "human_label": False, "relevance_score": 15},
    ]
    band_population = {"b00_19": 100, "b20_39": 0, "b40_59": 0, "b60_79": 0, "b80_100": 0}
    block = _weighted_confusion_block(rows, band_population)
    assert block["confusion_weighted"]["tp"] == 50.0
    assert block["confusion_weighted"]["tn"] == 50.0
    assert block["labeled_count"] == 2


def test_metrics_by_version_groups_correctly():
    rows = [
        {"is_relevant": True, "human_label": True, "relevance_prompt_version": "rel-v1"},
        {"is_relevant": True, "human_label": False, "relevance_prompt_version": "rel-v2"},
        {"is_relevant": True, "human_label": True, "relevance_prompt_version": "rel-v1"},
    ]
    out = _metrics_by_version(rows)
    by_version = {o["version"]: o for o in out}
    assert set(by_version) == {"rel-v1", "rel-v2"}
    assert by_version["rel-v1"]["labeled_count"] == 2
    assert by_version["rel-v2"]["labeled_count"] == 1


def test_service_metrics_warns_when_zero_audit_labels():
    repo = _FakeBeritaRepo(
        confusion_rows=[{"is_relevant": True, "human_label": True, "relevance_score": 80, "relevance_prompt_version": "rel-v1"}],
        audit_rows=[],
    )
    svc = RelevanceFeedbackService(berita_repository=repo, label_event_repository=object(), audit_repository=object())
    payload, status = svc.metrics()
    assert status == 200
    assert payload["audit"] is None
    assert payload["bias"]["audit_labels"] == 0
    assert payload["bias"]["warning"]


def test_service_metrics_produces_audit_block_when_enough_labels():
    audit_rows = [
        {
            "is_relevant": True, "human_label": True, "relevance_score": 10,
            "relevance_prompt_version": "rel-v1", "label_source": "audit",
        }
        for _ in range(35)
    ]
    repo = _FakeBeritaRepo(
        confusion_rows=audit_rows,
        band_population={"b00_19": 35, "b20_39": 0, "b40_59": 0, "b60_79": 0, "b80_100": 0},
    )
    svc = RelevanceFeedbackService(berita_repository=repo, label_event_repository=object(), audit_repository=object())
    payload, status = svc.metrics()
    assert status == 200
    assert payload["audit"] is not None
    assert payload["bias"]["warning"] is None


def test_service_metrics_reads_confusion_rows_only_once():
    """Blok audit diturunkan dari daftar yang sama, bukan query kedua."""
    rows = [
        {
            "is_relevant": True, "human_label": True, "relevance_score": 90,
            "relevance_prompt_version": "rel-v1", "label_source": "targeted",
        },
        {
            "is_relevant": False, "human_label": True, "relevance_score": 30,
            "relevance_prompt_version": "rel-v1", "label_source": "audit",
        },
    ]
    repo = _FakeBeritaRepo(confusion_rows=rows)
    svc = RelevanceFeedbackService(berita_repository=repo, label_event_repository=object(), audit_repository=object())
    payload, _status = svc.metrics()

    assert repo.confusion_calls == 1
    assert payload["bias"]["audit_labels"] == 1
    assert payload["bias"]["targeted_labels"] == 1
