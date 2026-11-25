from processing import translate


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def answer(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def notice():
    return {
        "title": "Cybersecurity services", "description": "Scope",
        "buyer_country": "PL", "deadline": "2026-12-01", "estimated_value": 100000,
        "currency": "EUR", "cpv_codes": ["72212000"],
    }


def test_key_goes_in_header_not_url(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    client = Client([Response(200, answer("EN:\nOne\n\nPL:\nJeden"))])
    result = translate.summarize_notice(notice(), client=client)
    url, _, headers = client.calls[0]
    assert "secret-key" not in url
    assert headers["x-goog-api-key"] == "secret-key"
    assert result["summary_status"] == "generated"


def test_key_is_read_at_call_time(monkeypatch):
    client = Client([Response(200, answer("EN:\nOne\n\nPL:\nJeden"))])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert translate.summarize_notice(notice(), client=client)["summary_status"] == "unavailable"
    monkeypatch.setenv("GEMINI_API_KEY", "late-key")
    assert translate.summarize_notice(notice(), client=client)["summary_status"] == "generated"


def test_rate_limit_is_retried_with_backoff(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client = Client([
        Response(429), Response(503), Response(200, answer("EN:\nOne\n\nPL:\nJeden")),
    ])
    sleeps = []
    result = translate.summarize_notice(
        notice(), client=client, sleep=lambda seconds: sleeps.append(seconds))
    assert len(client.calls) == 3
    assert sleeps == [0.5, 1.0]
    assert result["summary_status"] == "generated"


def test_failure_never_becomes_a_fake_summary(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client = Client([Response(503), Response(503), Response(503)])
    result = translate.summarize_notice(
        notice(), client=client, sleep=lambda _: None)
    assert result["summary_status"] == "unavailable"
    assert result["summary_en"] == ""
    assert result["summary_pl"] == ""
    assert "Cybersecurity services" not in (result["summary_en"], result["summary_pl"])


def test_malformed_answer_is_flagged_not_promoted(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client = Client([Response(200, answer("just prose, no language sections"))])
    result = translate.summarize_notice(notice(), client=client)
    assert result["summary_status"] == "malformed"
    assert result["summary_en"] == ""
