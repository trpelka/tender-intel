import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from database.repository import Repository
from pipeline import RunResult
from api import main

# Replace the module-level repository before any request is made. The default
# repository points at the development database, which tests must never use.
_TEST_DB = Path(tempfile.mkdtemp(prefix="tender-api-")) / "api.db"
_TEST_REPO = Repository(f"sqlite:///{_TEST_DB}")
_TEST_REPO.create_schema()
main.repo = _TEST_REPO


def test_health_is_public():
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_run_endpoint_returns_the_pipeline_result(monkeypatch):
    monkeypatch.setattr(main, "run", lambda *a, **k: RunResult(
        notices_collected=3, unique=2, scored=2, stored=2,
        digest_items=2, digest_path="out/x.html"))
    response = TestClient(main.app).post("/runs", json={
        "profile": {"name": "API Client", "email": "a@b.com"},
        "dry_run": True, "no_translate": True})
    assert response.status_code == 200
    assert response.json()["stored"] == 2


def test_api_key_is_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("TENDER_API_KEY", "secret")
    anonymous = TestClient(main.app)
    assert anonymous.post("/runs", json={"profile": {"name": "X"}}).status_code == 401
    allowed = TestClient(main.app, headers={"X-API-Key": "secret"})
    assert allowed.get("/clients").status_code == 200
