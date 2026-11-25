import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import Intelligence
from database.repository import Repository
from pg import pg_uri


def sample(notice_id="N-1", hash_key="h-1", value=120000):
    return {
        "notice_id": notice_id, "source": "TED", "title": "Software",
        "cpv_codes": ["72212000"], "content_hash": hash_key,
        "estimated_value": value, "currency": "EUR",
        "relevance_score": 10, "impact": "HIGH", "summary_en": "A summary",
        "summary_status": "generated",
    }


@pytest.fixture
def repo(tmp_path):
    r = Repository(f"sqlite:///{tmp_path / 'repo.db'}")
    r.create_schema()
    return r


def test_store_run_is_idempotent(repo):
    client_id = repo.insert_client("Test", "a@b.com", {"keywords": ["software"]})
    assert repo.store_run([sample()], client_id) == 1
    assert repo.store_run([sample()], client_id) == 0
    assert len(repo.client_intelligence(client_id)) == 1


def test_failed_transaction_rolls_back(repo):
    client_id = repo.insert_client("Test", "a@b.com", {})
    with pytest.raises(IntegrityError):
        with repo.session() as session:
            session.add(Intelligence(notice_id=99999, client_id=client_id,
                                     relevance_score=1))
    with Session(repo.engine) as session:
        assert session.execute(select(Intelligence)).scalars().all() == []


def test_value_is_numeric_after_storage(repo):
    client_id = repo.insert_client("Test", "a@b.com", {})
    repo.store_run([sample(value=["120000"])], client_id)
    row = repo.client_intelligence(client_id)[0]
    assert row["estimated_value"] == 120000.0


def test_pg_uri_rewrites_a_socket_style_uri():
    from pathlib import Path

    class Info:
        def socket_path(self):
            return Path("/tmp/pgdir/.s.PGSQL.5432")

    class Server:
        def get_uri(self):
            return "postgresql://postgres:@/postgres?host=/tmp/pgdir"

        def get_postmaster_info(self):
            return Info()

    result = pg_uri(Server())
    assert result.startswith("postgresql+pg8000://postgres@/postgres?unix_sock=")
    assert "pgdir" in result and ".s.PGSQL.5432" in result

    class InfoV2:
        port = 5432
        socket_path = None

    class ServerV2:
        def get_uri(self):
            return "postgresql://postgres:@/postgres?host=/tmp/pgdir"

        def get_postmaster_info(self):
            return InfoV2()

    rewritten = pg_uri(ServerV2())
    assert "unix_sock=" in rewritten and "pgdir" in rewritten and ".s.PGSQL.5432" in rewritten


def test_postgresql_repository_roundtrip():
    pgserver = pytest.importorskip("pgserver")
    import tempfile
    server = pgserver.get_server(tempfile.mkdtemp(prefix="tender-repo-pg-"))
    repo = Repository(pg_uri(server))
    repo.create_schema()
    client_id = repo.insert_client("PG", "pg@example.com", {})
    assert repo.store_run([sample(hash_key="pg-1")], client_id) == 1
    assert repo.client_intelligence(client_id)[0]["title"] == "Software"
