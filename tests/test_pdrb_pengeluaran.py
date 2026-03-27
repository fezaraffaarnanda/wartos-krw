from ai.pdrb_pengeluaran import (
    PDRB_PENGELUARAN_LABELS,
    format_pdrb_pengeluaran_hasil,
    get_pdrb_pengeluaran_parent_code,
)


def test_format_pdrb_pengeluaran_hasil_formats_known_leaf_code():
    assert format_pdrb_pengeluaran_hasil("PKRT-01") == (
        "PKRT-01/Makanan dan minuman tidak beralkohol"
    )


def test_format_pdrb_pengeluaran_hasil_preserves_special_markers():
    assert format_pdrb_pengeluaran_hasil("Tidak Relevan") == "Tidak Relevan"
    assert format_pdrb_pengeluaran_hasil("—") == "—"


def test_parent_code_can_be_derived_from_leaf_code_prefix():
    assert get_pdrb_pengeluaran_parent_code("PKLNPRT-04") == "PKLNPRT"
    assert PDRB_PENGELUARAN_LABELS["PI-04"] == "Barang untuk Dijual Kembali (Goods for Resale)"
