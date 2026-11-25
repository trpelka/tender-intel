import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from database.models import make_engine
from pg import pg_uri

ROOT = Path(__file__).resolve().parents[1]


def _upgrade(url):
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def test_upgrade_head_on_sqlite(tmp_path):
    path = tmp_path / "mig.db"
    _upgrade(str(path))
    engine = create_engine(f"sqlite:///{path}")
    tables = set(inspect(engine).get_table_names())
    assert {"clients", "notices", "intelligence", "digests"} <= tables
    indexes = {i["name"] for i in inspect(engine).get_indexes("intelligence")}
    assert {"idx_intel_client", "idx_intel_notice"} <= indexes


def test_upgrade_head_on_postgresql():
    pgserver = pytest.importorskip("pgserver")
    import tempfile
    server = pgserver.get_server(tempfile.mkdtemp(prefix="tender-pg-"))
    url = pg_uri(server)
    _upgrade(url)
    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {"clients", "notices", "intelligence", "digests"} <= tables
    with engine.connect() as conn:
        version = conn.exec_driver_sql(
            "SELECT version_num FROM alembic_version").scalar()
    assert version
