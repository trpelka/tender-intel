from processing.relevance import (
    HIGH_VALUE_KEYWORDS,
    filter_and_score,
    impact_label,
    keyword_in_text,
    normalize_keyword,
    score,
)


def notice(**overrides):
    base = {
        "title": "",
        "description": "",
        "cpv_codes": [],
        "buyer_country": "PL",
        "estimated_value": None,
        "deadline": None,
    }
    base.update(overrides)
    return base


def profile(**overrides):
    base = {
        "cpv_codes": [],
        "keywords": [],
        "countries": [],
        "min_value": None,
        "min_relevance_score": 5,
    }
    base.update(overrides)
    return base


def test_exact_cpv_match_scores_eight():
    total, reasons = score(notice(cpv_codes=["72212000"]), profile(cpv_codes=["72212000"]))
    assert total == 8
    assert reasons[0].startswith("CPV")


def test_prefix_cpv_match_scores_two():
    total, _ = score(notice(cpv_codes=["72212000"]), profile(cpv_codes=["72"]))
    assert total == 2


def test_only_the_strongest_cpv_match_counts():
    total, reasons = score(
        notice(cpv_codes=["72212000", "48800000"]),
        profile(cpv_codes=["72", "48800000"]),
    )
    assert total == 8
    assert sum(1 for reason in reasons if reason.startswith("CPV")) == 1


def test_title_keyword_scoring_grows_and_caps():
    one, _ = score(notice(title="software platform"), profile(keywords=["software"]))
    two, _ = score(
        notice(title="software system platform"),
        profile(keywords=["software", "system"]),
    )
    three, _ = score(
        notice(title="software system digital platform"),
        profile(keywords=["software", "system", "digital"]),
    )
    assert one == 4
    assert two == 6
    assert three == 8


def test_high_value_security_keyword_adds_six():
    assert "cybersecurity" in HIGH_VALUE_KEYWORDS
    total, reasons = score(
        notice(title="cybersecurity audit for the ministry"),
        profile(keywords=["cybersecurity"]),
    )
    assert total == 6
    assert any(reason.startswith("high-title") for reason in reasons)


def test_description_hits_add_one_each_up_to_two():
    one, _ = score(
        notice(title="road works", description="software delivery"),
        profile(keywords=["software"]),
    )
    two, _ = score(
        notice(title="road works", description="software system"),
        profile(keywords=["software", "system"]),
    )
    assert one == 1
    assert two == 2


def test_country_match_adds_one():
    total, _ = score(notice(), profile(countries=["PL"]))
    assert total == 1


def test_value_below_minimum_forces_zero():
    total, reasons = score(
        notice(estimated_value=50000),
        profile(min_value=100000),
    )
    assert total == 0
    assert reasons == ["below minimum value"]


def test_missing_value_is_not_treated_as_zero():
    total, _ = score(notice(estimated_value=None), profile(min_value=100000, countries=["PL"]))
    assert total == 1


def test_impact_labels_match_the_documented_thresholds():
    assert impact_label(10) == "HIGH"
    assert impact_label(9) == "MEDIUM"
    assert impact_label(5) == "MEDIUM"
    assert impact_label(4) == "LOW"


def test_short_acronyms_need_token_boundaries():
    assert keyword_in_text("soc", "social media campaign") is False
    assert keyword_in_text("siem", "siemens building") is False
    assert keyword_in_text("soc", "24/7 soc monitoring") is True


def test_normalize_keyword_collapses_whitespace_and_case():
    assert normalize_keyword("  Cyber   SECURITY ") == "cyber security"


def test_expired_deadline_is_dropped():
    kept = filter_and_score(
        [
            notice(title="software", cpv_codes=["72212000"], deadline="2020-01-01T00:00:00Z"),
            notice(title="software", cpv_codes=["72212000"], deadline="2999-01-01T00:00:00Z"),
        ],
        profile(cpv_codes=["72212000"], min_relevance_score=1),
    )
    assert len(kept) == 1
    assert kept[0]["deadline"].startswith("2999")


def test_unparseable_deadline_is_kept():
    kept = filter_and_score(
        [notice(title="software", cpv_codes=["72212000"], deadline="not-a-date")],
        profile(cpv_codes=["72212000"], min_relevance_score=1),
    )
    assert len(kept) == 1


def test_results_are_filtered_by_min_score_and_sorted_descending():
    strong = notice(title="software system digital", cpv_codes=["72212000"])
    weak = notice(title="road works", cpv_codes=["45000000"])
    kept = filter_and_score([weak, strong], profile(keywords=["software", "system", "digital"], min_relevance_score=5))
    assert [item["relevance_score"] for item in kept] == sorted(
        [item["relevance_score"] for item in kept], reverse=True
    )
    assert strong["impact"] in {"HIGH", "MEDIUM"}
    assert weak not in kept


def test_buyer_country_list_is_joined_for_the_digest():
    kept = filter_and_score(
        [notice(title="software", buyer_country=["PL", "CZ"])],
        profile(cpv_codes=["72212000"], countries=["PL"], min_relevance_score=1),
    )
    assert kept[0]["buyer_country"] == "PL,CZ"
