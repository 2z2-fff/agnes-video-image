"""Persistent generation history.

Every image/video generation gets a record in ``uploads/history.json`` so the
UI can restore results after a page reload, and completed videos are downloaded
into ``uploads/videos/`` so they no longer depend on Agnes' temporary URLs.
"""

import json
import logging
import threading
import time
import uuid

from app.config import HISTORY_FILE, MAX_HISTORY_RECORDS, UPLOADS_DIR

logger = logging.getLogger(__name__)

_lock = threading.Lock()


# ─── Low-level storage ─────────────────────────────────────────────


def _load() -> list[dict]:
    """Read all records (newest first). Corrupt files degrade to an empty list."""
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write(records: list[dict]) -> None:
    """Atomically replace the history file.

    Failures are swallowed on purpose: history is a convenience, and losing it
    must never break a generation that already cost money.
    """
    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = HISTORY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(HISTORY_FILE)
    except OSError as exc:
        logger.warning("History write failed (%s); continuing without persistence", exc)


# ─── Public API ───────────────────────────────────────────────────


def add_record(kind: str, **fields) -> dict:
    """Create a record for a new generation and return it."""
    record = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,                 # "image" | "video"
        "created_at": int(time.time()),
        "status": "queued",
        "local_url": None,            # /uploads/... once persisted
        "remote_url": None,           # Agnes URL
        "error": None,
        **fields,
    }
    with _lock:
        records = _load()
        records.insert(0, record)
        del records[MAX_HISTORY_RECORDS:]
        _write(records)
    return record


def update_record(record_id: str | None = None, task_id: str | None = None, **fields) -> dict | None:
    """Patch a record by its id or by its Agnes task id."""
    with _lock:
        records = _load()
        hit = None
        for rec in records:
            if (record_id and rec.get("id") == record_id) or (
                task_id and rec.get("task_id") == task_id
            ):
                rec.update(fields)
                hit = rec
                break
        if hit is not None:
            _write(records)
    return hit


def find_by_task(task_id: str) -> dict | None:
    """Look up a record by Agnes task id."""
    for rec in _load():
        if rec.get("task_id") == task_id:
            return rec
    return None


def get_record(record_id: str) -> dict | None:
    """Look up a record by its local id (used as the job id)."""
    for rec in _load():
        if rec.get("id") == record_id:
            return rec
    return None


def list_records(limit: int = 50, kind: str | None = None) -> list[dict]:
    """Return the newest records, optionally filtered by kind."""
    records = _load()
    if kind:
        records = [r for r in records if r.get("kind") == kind]
    return records[:limit]


def delete_record(record_id: str) -> bool:
    """Remove a record (the stored file is kept on disk)."""
    with _lock:
        records = _load()
        kept = [r for r in records if r.get("id") != record_id]
        if len(kept) == len(records):
            return False
        _write(kept)
    return True
