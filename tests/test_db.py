import sqlite3

import pytest

from database import db


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "tender.db"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    return path


def test_foreign_keys_are_enforced(database):
    conn = db.get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO intelligence (notice_id, client_id, relevance_score) "
            "VALUES (99999, 1, 5)"
        )
    conn.close()


def test_estimated_value_is_stored_as_a_number(database):
    notice = {
        "notice_id": "X-1", "source": "TED", "title": "Test",
        "cpv_codes": [], "estimated_value": ["120000"],
        "currency": "EUR", "content_hash": "hash-1",
    }
    db.insert_notice(notice)
    conn = db.get_conn()
    value = conn.execute(
        "SELECT estimated_value FROM notices WHERE content_hash='hash-1'"
    ).fetchone()[0]
    conn.close()
    assert isinstance(value, float)
    assert value == 120000.0


def test_unparseable_value_is_null_not_a_string(database):
    notice = {
        "notice_id": "X-2", "source": "TED", "title": "Test",
        "cpv_codes": [], "estimated_value": ["about 1 million"],
        "content_hash": "hash-2",
    }
    db.insert_notice(notice)
    conn = db.get_conn()
    value = conn.execute(
        "SELECT estimated_value FROM notices WHERE content_hash='hash-2'"
    ).fetchone()[0]
    conn.close()
    assert value is None


def test_schema_version_and_migration_are_idempotent(database):
    db.init_db()
    conn = db.get_conn()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    indexes = {row["name"] for row in conn.execute("PRAGMA index_list('intelligence')")}
    assert "idx_intel_notice" in indexes
    conn.close()
