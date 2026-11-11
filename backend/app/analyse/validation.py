"""Visual validation of the built-up layer: random cells checked by a person on imagery.

The PoC brief sets the success criterion: **≥ 80 % agreement on 50 cells checked visually**
(ideally on very high resolution imagery — Pléiades Neo from SEAS Guyane). This module
draws a reproducible, stratified sample of cells (half predicted built, half predicted
not built in the neighbourhood of the settlement, where confusion happens), records each
verdict and computes the agreement.

A cell is *predicted built* when its fused built share is ≥ 20 % the year checked.
"""

from __future__ import annotations

import datetime
import random
from typing import Any, Dict, List, Optional

from app.analyse import builtup
from app.analyse.grid import cell_bounds, cell_center, cell_id, parse_cell
from app.config import Settings, get_settings
from app.core import audit
from app.db import db, read_db, rows

BUILT_THRESHOLD = 0.2
SAMPLE_SIZE = 50
TARGET = 0.8
VERDICTS = {"bati": "Bâti", "non_bati": "Non bâti", "incertain": "Incertain"}


def sample(commune: str, year: int, settings: Optional[Settings] = None, size: int = SAMPLE_SIZE) -> List[Dict[str, Any]]:
    """Reproducible stratified sample (same commune + year → same cells for everybody)."""
    cfg = settings or get_settings()
    data = builtup.load(commune, cfg)
    if data is None:
        return []
    year = builtup.nearest_year(data["years"], year)
    values = builtup.year_values(data, year)
    built = sorted(c for c, v in values.items() if v >= BUILT_THRESHOLD)
    near: set = set()
    for c in built:
        r, col = parse_cell(c)
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                n = cell_id(r + dr, col + dc)
                if values.get(n, 0.0) < 0.05:
                    near.add(n)
    rng = random.Random(f"{commune}:{year}")
    half = size // 2
    picked = rng.sample(built, min(half, len(built))) + rng.sample(sorted(near), min(size - min(half, len(built)), len(near)))
    rng.shuffle(picked)
    out = []
    for c in picked:
        lon, lat = cell_center(*parse_cell(c))
        out.append({"cell": c, "lat": round(lat, 6), "lon": round(lon, 6), "bounds": cell_bounds(*parse_cell(c)),
                    "predicted_share": round(values.get(c, 0.0), 3)})
    return out


def record(commune: str, cell: str, year: int, verdict: str, imagery: str, user: Dict[str, Any],
           settings: Optional[Settings] = None) -> None:
    cfg = settings or get_settings()
    if verdict not in VERDICTS:
        raise ValueError("Verdict inconnu")
    data = builtup.load(commune, cfg)
    if data is None:
        raise LookupError("Analyse du bâti non réalisée pour cette commune")
    year = builtup.nearest_year(data["years"], year)
    predicted = builtup.year_values(data, year).get(cell, 0.0)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db(cfg) as conn:
        conn.execute(
            "INSERT INTO validations (commune_code, cell, year, predicted, verdict, imagery, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(commune_code, cell, year, created_by) DO UPDATE SET "
            "verdict = excluded.verdict, imagery = excluded.imagery, predicted = excluded.predicted, created_at = excluded.created_at",
            (commune, cell, year, predicted, verdict, imagery[:80], now, user["username"]),
        )
    audit.record("validation.record", actor=user["username"], target=f"commune:{commune}",
                 details={"cell": cell, "year": year, "verdict": verdict, "imagery": imagery[:80]}, settings=cfg)


def report(commune: str, year: Optional[int] = None, settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Agreement between the platform and the visual checks (uncertain verdicts excluded)."""
    cfg = settings or get_settings()
    query, params = "SELECT * FROM validations WHERE commune_code = ?", [commune]
    if year:
        query += " AND year = ?"
        params.append(year)
    with read_db(cfg) as conn:
        entries = rows(conn.execute(query + " ORDER BY created_at DESC", params).fetchall())
    decided = [e for e in entries if e["verdict"] != "incertain"]
    agree = [e for e in decided if (e["predicted"] >= BUILT_THRESHOLD) == (e["verdict"] == "bati")]
    built_pred = [e for e in decided if e["predicted"] >= BUILT_THRESHOLD]
    rate = len(agree) / len(decided) if decided else None
    return {
        "checked": len(entries), "decided": len(decided), "uncertain": len(entries) - len(decided),
        "agreement": round(rate, 3) if rate is not None else None, "target": TARGET, "sample_size": SAMPLE_SIZE,
        "reached": bool(rate is not None and len(decided) >= SAMPLE_SIZE * 0.8 and rate >= TARGET),
        "false_built": sum(1 for e in built_pred if e["verdict"] == "non_bati"),
        "missed_built": sum(1 for e in decided if e["predicted"] < BUILT_THRESHOLD and e["verdict"] == "bati"),
        "entries": [{k: e[k] for k in ("cell", "year", "predicted", "verdict", "imagery", "created_by", "created_at")} for e in entries],
        "rule": f"carreau « bâti » pour la plateforme si sa part bâtie fusionnée ≥ {int(BUILT_THRESHOLD * 100)} %",
    }
