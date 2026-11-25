"""SQLAlchemy models shared by the repository and Alembic migrations.

The same metadata must work on SQLite (local, zero setup) and PostgreSQL
(deployment). Keep column types portable: no SQLite-only types and no
PostgreSQL-only types in the declarative layer.
"""
from __future__ import annotations

import os

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def database_url(url: str | None = None) -> str:
    value = (url or os.getenv("DATABASE_URL", "tender_intel.db")).strip()
    if "://" not in value:
        return f"sqlite:///{value}"
    # pg8000 is a declared dependency and needs no system libraries. Ordinary
    # postgres:// URLs should work without the caller knowing the driver name.
    if value.startswith("postgresql://"):
        return "postgresql+pg8000://" + value[len("postgresql://"):]
    return value


def make_engine(url: str | None = None):
    resolved = database_url(url)
    if resolved.startswith("sqlite"):
        engine = create_engine(resolved, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(resolved, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    profile: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (
        Index("idx_hash", "content_hash"),
        Index("idx_notice_id", "notice_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notice_id: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    cpv_codes: Mapped[str] = mapped_column(Text, default="")
    buyer_name: Mapped[str] = mapped_column(String(512), default="")
    buyer_country: Mapped[str] = mapped_column(String(128), default="")
    publication_date: Mapped[str] = mapped_column(String(64), default="")
    deadline: Mapped[str] = mapped_column(String(64), default="")
    estimated_value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(16), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    notice_type: Mapped[str] = mapped_column(String(64), default="")
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False)
    collected_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)


class Intelligence(Base):
    __tablename__ = "intelligence"
    __table_args__ = (
        Index("idx_intel_client", "client_id"),
        Index("idx_intel_notice", "notice_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notices.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False)
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_en: Mapped[str] = mapped_column(Text, default="")
    summary_pl: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    summary_status: Mapped[str] = mapped_column(String(32), default="generated")
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, nullable=False)
    period_from: Mapped[str] = mapped_column(String(64), default="")
    period_to: Mapped[str] = mapped_column(String(64), default="")
    html: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[str | None] = mapped_column(DateTime)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)
