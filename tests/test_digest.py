from reports.digest import generate


def notice(**overrides):
    base = {
        "title": "Supply of servers",
        "description": "A short description",
        "url": "https://example.com/tender/1",
        "impact": "HIGH",
        "buyer_country": "PL",
        "estimated_value": 120000.0,
        "currency": "EUR",
        "deadline": "2026-12-01",
        "cpv_codes": ["48800000"],
    }
    base.update(overrides)
    return base


def render(notices):
    return generate("Test Client", notices, "2026-11-01", "2026-11-07")


def test_html_escapes_untrusted_titles_and_summaries():
    html = render([notice(title="<script>alert(1)</script>", description="<b>bold</b>")])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_javascript_urls_are_replaced_with_an_anchor():
    html = render([notice(url="javascript:alert(1)")])
    assert "javascript:" not in html
    assert 'href="#"' in html


def test_http_urls_are_preserved():
    html = render([notice(url="https://example.com/tender?id=1&lang=en")])
    assert "https://example.com/tender?id=1&amp;lang=en" in html


def test_unknown_impact_falls_back_to_low_instead_of_crashing():
    html = render([notice(impact="critical")])
    assert ">LOW<" in html


def test_string_value_does_not_crash_formatting():
    html = render([notice(estimated_value="120000")])
    assert "120,000 EUR" in html


def test_unparseable_value_renders_a_dash():
    html = render([notice(estimated_value="not-a-number")])
    assert "<b>Value:</b> —" in html


def test_cpv_list_loaded_from_json_string():
    html = render([notice(cpv_codes='["48800000", "72212000"]')])
    assert "48800000, 72212000" in html


def test_client_name_and_period_are_escaped():
    html = generate("<Client>", [], "2026-11-01", "2026-11-07")
    assert "&lt;Client&gt;" in html


def test_empty_digest_states_that_there_are_no_tenders():
    html = render([])
    assert "No relevant tenders this week." in html
    assert "0 relevant tenders" in html
