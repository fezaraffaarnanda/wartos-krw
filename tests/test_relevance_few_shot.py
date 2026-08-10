from repositories.berita import BeritaRepository
from services.relevance_feedback_service import RelevanceFeedbackService


class _FakeBeritaLabeled:
    def __init__(self, rows):
        self._rows = rows

    def list_labeled_rows(self, *, limit=1000, include_content=False, label_source=None):
        return self._rows


def _row(id_, score, is_relevant, human_label, title="T"):
    return {
        "id": id_, "title": title, "relevance_score": score, "is_relevant": is_relevant,
        "human_label": human_label, "relevance_reason": "r", "content": "c", "source": "s",
    }


def test_disagreement_export_rows_method_removed():
    """Defect lama: list_disagreement_export_rows() pre-slice limit*3 lalu
    ORDER BY score ASC lalu filter di Python -- FP skor tinggi (mesin percaya
    diri tapi salah) tak pernah terjangkau. Dihapus, bukan diperbaiki di
    tempat, supaya jalur lama tidak bisa diam-diam dipakai lagi."""
    assert not hasattr(BeritaRepository, "list_disagreement_export_rows")


def test_no_corrections_message_when_zero_disagreement():
    """Kasus live saat ini: 19 label, 0 koreksi. Versi lama balas 'Belum ada
    disagreement' dan berhenti di situ. Versi baru tetap membangun konten
    dari konfirmasi."""
    rows = [_row(1, 80, True, True), _row(2, 10, False, False)]
    svc = RelevanceFeedbackService(
        berita_repository=_FakeBeritaLabeled(rows),
        label_event_repository=object(), audit_repository=object(),
    )
    payload, status = svc.export_few_shot(limit=10)
    assert status == 200
    assert payload["total_labels"] == 2
    assert payload["corrections"]["false_positives"] == []
    assert payload["corrections"]["false_negatives"] == []
    assert "Belum ada koreksi" in payload["formatted_prompt"]
    assert len(payload["confirmations"]) == 2


def test_high_score_false_positive_is_reachable():
    """Inti defect: satu FP dengan skor 95 di antara banyak baris skor rendah
    tetap harus terpilih -- pre-slice lama akan menguburnya."""
    rows = [_row(i, 5, False, False) for i in range(30)]
    rows.append(_row(999, 95, True, False))
    svc = RelevanceFeedbackService(
        berita_repository=_FakeBeritaLabeled(rows),
        label_event_repository=object(), audit_repository=object(),
    )
    payload, status = svc.export_few_shot(limit=5)
    assert status == 200
    fp_ids = {r["id"] for r in payload["corrections"]["false_positives"]}
    assert 999 in fp_ids


def test_round_robin_picks_across_all_bands():
    rows = [
        _row(1, 5, True, False),
        _row(2, 25, True, False),
        _row(3, 45, True, False),
        _row(4, 65, True, False),
        _row(5, 95, True, False),
    ]
    svc = RelevanceFeedbackService(
        berita_repository=_FakeBeritaLabeled(rows),
        label_event_repository=object(), audit_repository=object(),
    )
    payload, status = svc.export_few_shot(limit=5)
    picked_ids = {r["id"] for r in payload["corrections"]["false_positives"] + payload["corrections"]["false_negatives"]}
    assert picked_ids == {1, 2, 3, 4, 5}


def test_confirmations_prefer_low_uncertainty():
    """Kasus sulit (skor dekat 50) yang mesin sudah benar diprioritaskan
    sebagai anchor -- paling bernilai saat tidak ada koreksi sama sekali."""
    rows = [
        _row(1, 50, True, True),   # uncertainty 0 -- paling sulit
        _row(2, 5, False, False),  # uncertainty 45
        _row(3, 95, True, True),   # uncertainty 45
    ]
    svc = RelevanceFeedbackService(
        berita_repository=_FakeBeritaLabeled(rows),
        label_event_repository=object(), audit_repository=object(),
    )
    payload, status = svc.export_few_shot(limit=1)
    assert status == 200
    assert len(payload["confirmations"]) == 1
    assert payload["confirmations"][0]["id"] == 1
