"""Repository layer: one transaction per pipeline run.

Raw SQL scattered through the pipeline made it impossible to say where a
transaction began or ended. Here every write goes through a session context
manager that commits once or rolls back completely. `store_run` is atomic: a
crash halfway through cannot leave notices without their intelligence rows.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import numeric, scalar
from .models import Base, Client, Intelligence, Notice, make_engine


class Repository:
    def __init__(self, url: str | None = None):
        self.engine = make_engine(url)

    def create_schema(self) -> None:
        """Test/bootstrap convenience. Deployments use `alembic upgrade head`."""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self):
        with Session(self.engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def clients(self) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(Client).where(Client.active.is_(True))).scalars().all()
            return [{"id": r.id, "name": r.name, "email": r.email,
                     "profile": r.profile} for r in rows]

    def insert_client(self, name: str, email: str, profile: dict) -> int:
        with self.session() as session:
            client = Client(name=scalar(name), email=scalar(email),
                            profile=json.dumps(profile, ensure_ascii=False))
            session.add(client)
            session.flush()
            return client.id

    def find_client(self, name: str) -> dict | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(Client).where(Client.name == name)).scalars().first()
            return {"id": row.id, "name": row.name, "email": row.email,
                    "profile": row.profile} if row else None

    def _notice_row(self, n: dict) -> Notice:
        return Notice(
            notice_id=scalar(n.get("notice_id", "")),
            source=scalar(n.get("source", "")),
            title=scalar(n.get("title", "")),
            description=scalar(n.get("description", "")),
            cpv_codes=json.dumps(n.get("cpv_codes", []), ensure_ascii=False),
            buyer_name=scalar(n.get("buyer_name", "")),
            buyer_country=scalar(n.get("buyer_country", "")),
            publication_date=scalar(n.get("publication_date", "")),
            deadline=scalar(n.get("deadline", "")),
            estimated_value=numeric(n.get("estimated_value")),
            currency=scalar(n.get("currency", "")),
            url=scalar(n.get("url", "")),
            notice_type=scalar(n.get("notice_type", "")),
            content_hash=scalar(n.get("content_hash", "")),
        )

    def store_run(self, notices: list[dict], client_id: int) -> int:
        """Store notices and intelligence for one client in one transaction."""
        stored = 0
        with self.session() as session:
            for n in notices:
                digest = n.get("content_hash", "")
                existing = session.execute(
                    select(Notice).where(Notice.content_hash == digest)
                ).scalars().first()
                if existing is None:
                    existing = self._notice_row(n)
                    session.add(existing)
                    session.flush()

                already = session.execute(
                    select(Intelligence).where(
                        Intelligence.notice_id == existing.id,
                        Intelligence.client_id == client_id)
                ).scalars().first()
                if already is not None:
                    continue

                session.add(Intelligence(
                    notice_id=existing.id,
                    client_id=client_id,
                    relevance_score=int(n.get("relevance_score", 0)),
                    summary_en=scalar(n.get("summary_en", "")),
                    summary_pl=scalar(n.get("summary_pl", "")),
                    impact=scalar(n.get("impact", "MEDIUM")),
                    summary_status=scalar(n.get("summary_status", "generated")),
                ))
                stored += 1
        return stored

    def client_intelligence(self, client_id: int, days_back: int = 7) -> list[dict]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_back)
        with Session(self.engine) as session:
            rows = session.execute(
                select(Intelligence, Notice)
                .join(Notice, Notice.id == Intelligence.notice_id)
                .where(Intelligence.client_id == client_id,
                       Intelligence.created_at >= cutoff)
                .order_by(Intelligence.relevance_score.desc())
            ).all()
            return [
                {**{k: getattr(i, k) for k in (
                    "id", "notice_id", "client_id", "relevance_score",
                    "summary_en", "summary_pl", "impact", "summary_status")},
                 **{k: getattr(n, k) for k in (
                     "title", "buyer_name", "buyer_country", "deadline",
                     "estimated_value", "currency", "url", "cpv_codes")}}
                for i, n in rows
            ]
