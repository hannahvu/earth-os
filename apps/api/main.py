from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from apps.api.storage.db import get_events
from models.event import EarthEvent

app = FastAPI(title="EarthOS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/events", response_model=List[EarthEvent])
def list_events(
    region: Optional[str] = Query(None, description="Filter by BA code, e.g. ERCO"),
    limit: int = Query(500, ge=1, le=5000, description="Max rows to return"),
) -> List[EarthEvent]:
    db_path = os.environ.get("EARTHOS_DB", "earthos.db")
    return get_events(db_path, region=region, limit=limit)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
