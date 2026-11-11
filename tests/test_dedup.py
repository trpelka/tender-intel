from processing.dedup import deduplicate, make_hash, normalize_title, procurement_key


def notice(**overrides):
    base = {
        "source": "TED",
        "notice_id": None,
        "title": "Supply of servers",
        "buyer_name": "Ministry of Finance",
        "buyer_country": "PL",
        "estimated_value": 120000,
        "publication_date": "2026-11-01",
    }
    base.update(overrides)
    return base


def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title("Supply of: Servers (2026)!") == "supply of servers 2026"


def test_normalize_title_collapses_whitespace():
    assert normalize_title("  Supply   of\tservers ") == "supply of servers"


def test_same_notice_id_and_source_is_deduplicated():
    notices = [notice(notice_id="123"), notice(notice_id="123")]
    assert len(deduplicate(notices)) == 1


def test_same_notice_id_from_different_sources_has_a_different_hash():
    assert make_hash(notice(notice_id="123", source="TED")) != make_hash(notice(notice_id="123", source="BZP"))


def test_same_procurement_from_two_sources_is_still_collapsed():
    notices = [notice(notice_id="123", source="TED"), notice(notice_id="456", source="BZP")]
    assert len(deduplicate(notices)) == 1


def test_same_procurement_is_deduplicated_even_with_new_ids():
    notices = [
        notice(notice_id="a", estimated_value=120000),
        notice(notice_id="b", estimated_value=120040),
    ]
    assert len(deduplicate(notices)) == 1


def test_different_value_keeps_both_rows():
    notices = [
        notice(notice_id="a", estimated_value=120000),
        notice(notice_id="b", estimated_value=220000),
    ]
    assert len(deduplicate(notices)) == 2


def test_different_buyer_keeps_both_rows():
    notices = [
        notice(notice_id="a", buyer_name="Ministry of Finance"),
        notice(notice_id="b", buyer_name="Ministry of Health"),
    ]
    assert len(deduplicate(notices)) == 2


def test_hash_is_stable_for_the_same_input():
    assert make_hash(notice(notice_id="123")) == make_hash(notice(notice_id="123", title="Other title"))


def test_procurement_key_rounds_values_to_hundreds():
    assert procurement_key(notice(estimated_value=120049)) == procurement_key(notice(estimated_value=120000))


def test_content_hash_is_attached_to_every_kept_notice():
    kept = deduplicate([notice(notice_id="a")])
    assert len(kept[0]["content_hash"]) == 64
