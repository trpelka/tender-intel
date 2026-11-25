"""Use the Alembic migrations as the single way to create or upgrade a schema."""
from __future__ import annotations

from pathlib import Path

from .models import database_url


def upgrade(url: str | None = None) -> None:
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url(url).replace("%", "%%"))
    command.upgrade(config, "head")
