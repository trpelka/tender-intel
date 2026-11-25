from pathlib import Path

from collectors import bzp, ted
from database.repository import Repository
from pipeline import run


def notice(source, identifier, title):
    return {
        "source": source, "notice_id": identifier, "title": title,
        "description": "software delivery", "cpv_codes": ["72212000"],
        "buyer_name": "Ministry", "buyer_country": "PL",
        "estimated_value": 200000, "currency": "EUR", "url": "https://example.test/n",
    }


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(ted, "collect", lambda profile: [notice("TED", "T1", "software platform")])
    monkeypatch.setattr(bzp, "collect", lambda profile: [notice("BZP", "B1", "software system")])
    repo = Repository(f"sqlite:///{tmp_path / 'pipeline.db'}")
    repo.create_schema()
    client_id = repo.insert_client("Test Client", "a@b.com", {})
    profile = {"name": "Test Client", "email": "a@b.com", "keywords": ["software"],
               "cpv_codes": ["72212000"], "countries": ["PL"],
               "days_back": 7, "min_relevance_score": 1}
    return repo, client_id, profile


def test_dry_run_writes_digest_but_no_database_rows(monkeypatch, tmp_path):
    repo, client_id, profile = setup(monkeypatch, tmp_path)
    result = run(profile, client_id, dry_run=True, no_translate=True,
                 out_dir=str(tmp_path / "out"), repo=repo)
    assert result.notices_collected == 2
    assert result.scored >= 1
    assert result.stored == 0
    assert Path(result.digest_path).exists()


def test_normal_run_stores_once_and_builds_digest(monkeypatch, tmp_path):
    repo, client_id, profile = setup(monkeypatch, tmp_path)
    first = run(profile, client_id, out_dir=str(tmp_path / "out"), repo=repo)
    second = run(profile, client_id, out_dir=str(tmp_path / "out"), repo=repo)
    assert first.stored >= 1
    assert second.stored == 0
    assert Path(second.digest_path).exists()
