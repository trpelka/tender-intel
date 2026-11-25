"""HTTP surface for the tender pipeline (same engine as the CLI)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from database.migrations import upgrade
from database.models import database_url
from database.repository import Repository
from pipeline import run

repo = Repository()


def require_key(x_api_key: Optional[str] = Header(default=None)):
    key = os.getenv("TENDER_API_KEY", "").strip()
    if key and x_api_key != key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@asynccontextmanager
async def lifespan(_app):
    upgrade()
    yield


app = FastAPI(title="Tender Intelligence API", lifespan=lifespan)


class RunRequest(BaseModel):
    profile: dict
    dry_run: bool = True
    no_translate: bool = True
    out_dir: str = "output"


@app.get("/health")
def health():
    return {"status": "ok", "database": database_url()}


@app.get("/clients", dependencies=[Depends(require_key)])
def clients():
    return repo.clients()


@app.post("/runs", dependencies=[Depends(require_key)])
def start_run(request: RunRequest):
    profile = request.profile
    if not profile.get("name"):
        raise HTTPException(status_code=422, detail="profile.name is required")
    match = repo.find_client(profile["name"])
    client_id = match["id"] if match else repo.insert_client(
        profile["name"], profile.get("email", ""), profile)
    result = run(profile, client_id, dry_run=request.dry_run,
                 no_translate=request.no_translate, out_dir=request.out_dir,
                 repo=repo)
    return result.__dict__
