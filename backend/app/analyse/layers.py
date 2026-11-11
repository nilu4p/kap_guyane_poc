"""Storage of the grid layers of each commune (sparse JSON, one row per layer)."""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, Optional, Tuple

from app.config import Settings
from app.db import db, read_db


def save(commune: str, layer: str, payload: Any, meta: Optional[Dict[str, Any]] = None,
         settings: Optional[Settings] = None) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db(settings) as conn:
        conn.execute(
            "INSERT INTO grid_layers (commune_code, layer, computed_at, meta, payload) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(commune_code, layer) DO UPDATE SET computed_at = excluded.computed_at, "
            "meta = excluded.meta, payload = excluded.payload",
            (commune, layer, now, json.dumps(meta or {}), json.dumps(payload, separators=(",", ":"))),
        )


def load(commune: str, layer: str, settings: Optional[Settings] = None) -> Optional[Tuple[Any, Dict[str, Any], str]]:
    """(payload, meta, computed_at) or None."""
    with read_db(settings) as conn:
        row = conn.execute(
            "SELECT payload, meta, computed_at FROM grid_layers WHERE commune_code = ? AND layer = ?", (commune, layer)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload"]), json.loads(row["meta"] or "{}"), row["computed_at"]


def inventory(commune: str, settings: Optional[Settings] = None) -> Dict[str, Dict[str, Any]]:
    with read_db(settings) as conn:
        rows = conn.execute("SELECT layer, computed_at, meta FROM grid_layers WHERE commune_code = ?", (commune,)).fetchall()
    return {r["layer"]: {"computed_at": r["computed_at"], "meta": json.loads(r["meta"] or "{}")} for r in rows}


def analysed_communes(settings: Optional[Settings] = None) -> Dict[str, str]:
    """{commune code: computed_at} of the communes whose built-up analysis exists (light query)."""
    with read_db(settings) as conn:
        rows_ = conn.execute("SELECT commune_code, computed_at FROM grid_layers WHERE layer = 'builtup'").fetchall()
    return {r["commune_code"]: r["computed_at"] for r in rows_}
