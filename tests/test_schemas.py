from schemas.auth import LoginPayload, ResetPasswordPayload
from schemas.berita import BeritaFilterQuery
from schemas.scraping import ScrapeTriggerPayload


def test_berita_filter_query_normalization_defaults_and_sort():
    query = BeritaFilterQuery.from_request_args(
        {
            "search": "  pangan  ",
            "kbli_code": " c ",
            "page": "bukan-angka",
            "per_page": "9999",
            "sort_by": "date",
            "sort_dir": "asc",
        }
    )

    assert query.search == "pangan"
    assert query.kbli_code == "C"
    assert query.page == 1
    assert query.per_page == 100

    sort_col, sort_desc, sort_dir = query.resolve_sort()
    assert sort_col == "date_parsed"
    assert sort_desc is False
    assert sort_dir == "asc"


def test_auth_payload_normalization():
    login = LoginPayload.from_body({"username": "  Admin ", "password": " x "})
    reset = ResetPasswordPayload.from_body({"username": " User ", "code": "ab12cd34"})

    assert login.username == "admin"
    assert login.password == "x"
    assert reset.username == "user"
    assert reset.code == "AB12CD34"


def test_scrape_payload_clamps_invalid_values():
    payload_low = ScrapeTriggerPayload.from_body({"max_articles": "0"})
    payload_invalid = ScrapeTriggerPayload.from_body({"max_articles": "abc"})
    payload_high = ScrapeTriggerPayload.from_body({"max_articles": "99999"})

    assert payload_low.max_articles == 1
    assert payload_invalid.max_articles == 150
    assert payload_high.max_articles == 999
