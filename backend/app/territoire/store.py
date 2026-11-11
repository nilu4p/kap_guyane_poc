"""Persistence of the territorial reference data: communes, statistics, hypotheses, facilities."""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.config import Settings, get_settings
from app.db import db, read_db, row, rows

CATEGORIES: Dict[str, Dict[str, Any]] = {
    "ecole": {"label": "École (maternelle / élémentaire)", "demand": "enfants_3_10", "color": "#2563eb"},
    "college": {"label": "Collège", "demand": "enfants_11_14", "color": "#7c3aed"},
    "lycee": {"label": "Lycée", "demand": "jeunes_15_17", "color": "#a855f7"},
    "sante": {"label": "Santé (médecin, centre de santé, pharmacie)", "demand": "pop", "color": "#dc2626"},
    "eau": {"label": "Point d'eau potable (borne-fontaine)", "demand": "pop", "color": "#0891b2"},
    "alimentation": {"label": "Commerce alimentaire / marché", "demand": "pop", "color": "#ea580c"},
    "transport": {"label": "Transport (arrêt, gare routière, dégrad)", "demand": "pop", "color": "#16a34a"},
    "services": {"label": "Services publics (mairie annexe, poste, France services)", "demand": "pop", "color": "#475569"},
    "petite_enfance": {"label": "Petite enfance (crèche)", "demand": "pop", "color": "#db2777"},
}
STATUSES = ("existant", "provisoire", "projet")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --------------------------------------------------------------------------- communes


def upsert_communes(items: Sequence[Dict[str, Any]], source: str, settings: Optional[Settings] = None) -> int:
    now = _now()
    with db(settings) as conn:
        for c in items:
            conn.execute(
                "INSERT INTO communes (code, nom, epci, population, surface_ha, centre_lat, centre_lon, bbox, contour, source, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET nom = excluded.nom, epci = excluded.epci, "
                "population = excluded.population, surface_ha = excluded.surface_ha, centre_lat = excluded.centre_lat, "
                "centre_lon = excluded.centre_lon, bbox = excluded.bbox, contour = excluded.contour, source = excluded.source, "
                "updated_at = excluded.updated_at",
                (c["code"], c["nom"], c.get("epci", ""), c.get("population"), c.get("surface_ha"), c.get("centre_lat"),
                 c.get("centre_lon"), json.dumps(c.get("bbox") or []), json.dumps(c["contour"]), source, now),
            )
    return len(items)


def communes(settings: Optional[Settings] = None, with_contour: bool = False) -> List[Dict[str, Any]]:
    cols = "code, nom, epci, population, surface_ha, centre_lat, centre_lon, bbox, source, updated_at"
    if with_contour:
        cols += ", contour"
    with read_db(settings) as conn:
        out = rows(conn.execute(f"SELECT {cols} FROM communes ORDER BY nom").fetchall())
    for c in out:
        c["bbox"] = json.loads(c["bbox"] or "[]")
        if with_contour:
            c["contour"] = json.loads(c["contour"])
    return out


def commune(code: str, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    with read_db(settings) as conn:
        c = row(conn.execute("SELECT * FROM communes WHERE code = ?", (code,)).fetchone())
    if c:
        c["bbox"] = json.loads(c["bbox"] or "[]")
        c["contour"] = json.loads(c["contour"])
    return c


def ensure_communes(settings: Optional[Settings] = None) -> None:
    """First start: load the bundled commune boundaries (no network needed)."""
    from app.sources import geoapi

    cfg = settings or get_settings()
    with read_db(cfg) as conn:
        count = conn.execute("SELECT COUNT(*) FROM communes").fetchone()[0]
    if count == 0:
        upsert_communes(geoapi.communes(cfg, live=False), "geo.api.gouv.fr (instantané embarqué)", cfg)


# --------------------------------------------------------------------------- indicators


def replace_indicators(rows_: Iterable[Tuple[str, str, int, float, str]], settings: Optional[Settings] = None) -> int:
    now = _now()
    batch = [(geo, indicator, int(year), float(value), source, now) for geo, indicator, year, value, source in rows_]
    if not batch:
        return 0
    with db(settings) as conn:
        conn.executemany(
            "INSERT INTO indicators (geo, indicator, year, value, source, retrieved_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(geo, indicator, year) DO UPDATE SET value = excluded.value, source = excluded.source, "
            "retrieved_at = excluded.retrieved_at",
            batch,
        )
    return len(batch)


def series(geo: str, indicators: Optional[Sequence[str]] = None, settings: Optional[Settings] = None) -> Dict[str, Dict[int, float]]:
    """{indicator: {year: value}} for one geography."""
    query = "SELECT indicator, year, value FROM indicators WHERE geo = ?"
    params: List[Any] = [geo]
    if indicators:
        query += f" AND indicator IN ({','.join('?' for _ in indicators)})"
        params += list(indicators)
    with read_db(settings) as conn:
        result = conn.execute(query, params).fetchall()
    out: Dict[str, Dict[int, float]] = {}
    for r in result:
        if r["value"] is not None:
            out.setdefault(r["indicator"], {})[int(r["year"])] = float(r["value"])
    return out


def all_series(indicators: Sequence[str], settings: Optional[Settings] = None) -> Dict[str, Dict[str, Dict[int, float]]]:
    """{geo: {indicator: {year: value}}} for several indicators at once (comparisons, maps)."""
    with read_db(settings) as conn:
        result = conn.execute(
            f"SELECT geo, indicator, year, value FROM indicators WHERE indicator IN ({','.join('?' for _ in indicators)})",
            list(indicators),
        ).fetchall()
    out: Dict[str, Dict[str, Dict[int, float]]] = {}
    for r in result:
        if r["value"] is not None:
            out.setdefault(r["geo"], {}).setdefault(r["indicator"], {})[int(r["year"])] = float(r["value"])
    return out


def series_by_geo(settings: Optional[Settings] = None) -> Dict[str, Dict[str, Dict[int, float]]]:
    """{geo: {indicator: {year: value}}} of every indicator, in one query (KPI table of all communes)."""
    with read_db(settings) as conn:
        result = conn.execute("SELECT geo, indicator, year, value FROM indicators WHERE value IS NOT NULL").fetchall()
    out: Dict[str, Dict[str, Dict[int, float]]] = {}
    for r in result:
        out.setdefault(r["geo"], {}).setdefault(r["indicator"], {})[int(r["year"])] = float(r["value"])
    return out


def bpe(geo: str, settings: Optional[Settings] = None) -> Dict[str, float]:
    """Facility counts of the latest BPE vintage: {type code: count}."""
    with read_db(settings) as conn:
        result = conn.execute(
            "SELECT indicator, year, value FROM indicators WHERE geo = ? AND indicator LIKE 'bpe_%'", (geo,)
        ).fetchall()
    if not result:
        return {}
    latest = max(int(r["year"]) for r in result)
    return {r["indicator"][4:]: float(r["value"]) for r in result if int(r["year"]) == latest}


def data_freshness(settings: Optional[Settings] = None) -> Dict[str, Any]:
    with read_db(settings) as conn:
        result = conn.execute("SELECT source, COUNT(*) AS n, MAX(retrieved_at) AS at FROM indicators GROUP BY source").fetchall()
    return {r["source"]: {"values": r["n"], "retrieved_at": r["at"]} for r in result}


# --------------------------------------------------------------------------- hypotheses


def hypothesis(commune: str, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    with read_db(settings) as conn:
        return row(conn.execute("SELECT * FROM population_hypotheses WHERE commune_code = ?", (commune,)).fetchone())


def set_hypothesis(commune: str, data: Optional[Dict[str, Any]], actor: str, settings: Optional[Settings] = None) -> None:
    with db(settings) as conn:
        if not data:
            conn.execute("DELETE FROM population_hypotheses WHERE commune_code = ?", (commune,))
            return
        conn.execute(
            "INSERT INTO population_hypotheses (commune_code, year, value, low, high, source, note, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(commune_code) DO UPDATE SET year = excluded.year, "
            "value = excluded.value, low = excluded.low, high = excluded.high, source = excluded.source, note = excluded.note, "
            "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (commune, int(data["year"]), int(data["value"]), data.get("low"), data.get("high"), data.get("source", ""),
             data.get("note", ""), _now(), actor),
        )


# --------------------------------------------------------------------------- equipments


# Geolocation levels of the school directory that only place a facility at the town or
# locality centre: distances computed from them are unreliable.
IMPRECISE_PRECISIONS = ("Ville", "Lieu-dit", "Commune", "Centroïde de commune")

_SELECT = (
    "SELECT e.*, o.lat AS o_lat, o.lon AS o_lon, o.capacity AS o_capacity, o.capacity_unit AS o_unit, "
    "o.status AS o_status, o.note AS o_note, o.updated_by AS o_by, o.updated_at AS o_at "
    "FROM equipments e LEFT JOIN equipment_overrides o ON o.uid = e.uid"
)
_EFFECTIVE = {"lat": "COALESCE(o.lat, e.lat)", "lon": "COALESCE(o.lon, e.lon)", "status": "COALESCE(o.status, e.status)"}


def _equipment(r: Dict[str, Any]) -> Dict[str, Any]:
    """Facility as used everywhere: open-data values with the local corrections applied."""
    r = dict(r)
    r["attributes"] = json.loads(r.get("attributes") or "{}")
    override = {k: r.pop(k, None) for k in ("o_lat", "o_lon", "o_capacity", "o_unit", "o_status", "o_note", "o_by", "o_at")}
    corrected = []
    if override["o_lat"] is not None and override["o_lon"] is not None:
        r["source_position"] = [r["lat"], r["lon"]]
        r["lat"], r["lon"] = override["o_lat"], override["o_lon"]
        corrected.append("position")
    if override["o_capacity"] is not None:
        r["capacity"], r["capacity_unit"] = override["o_capacity"], override["o_unit"] or r.get("capacity_unit", "")
        corrected.append("capacité")
    if override["o_status"]:
        r["status"] = override["o_status"]
        corrected.append("statut")
    if override["o_note"]:
        r["attributes"]["note"] = override["o_note"]
    if corrected or override["o_note"]:
        r["correction"] = {"fields": corrected, "by": override["o_by"], "at": override["o_at"]}
    r["imprecise"] = (r["attributes"].get("precision") in IMPRECISE_PRECISIONS) and "position" not in corrected
    return r


# A sync may not remove more than this share of the facilities of a source at once: beyond,
# the source answer is suspect (partial extract, outage) and deletions are held back.
MAX_DELETION_SHARE = 0.3


def upsert_equipments(items: Sequence[Dict[str, Any]], source: str, actor: str = "system",
                      settings: Optional[Settings] = None, replace_source: bool = True) -> Dict[str, Any]:
    """Insert / refresh open-data facilities; facilities of that source no longer published are removed.

    Facilities entered by the services (source ``saisie``) are never touched by a sync. When the
    removals would exceed :data:`MAX_DELETION_SHARE` of the source (and more than 10 facilities),
    nothing is removed and the report says so (``deletion_held``).
    """
    now = _now()
    uids = [e["uid"] for e in items]
    batch = [(e["uid"], e["category"], e.get("subtype", ""), e.get("name", ""), e.get("commune"), e["lat"], e["lon"],
              e.get("capacity"), e.get("capacity_unit", ""), e.get("status", "existant"), source,
              json.dumps(e.get("attributes") or {}), now, actor) for e in items]
    with db(settings) as conn:
        if batch:
            conn.executemany(
                "INSERT INTO equipments (uid, category, subtype, name, commune_code, lat, lon, capacity, capacity_unit, status, source, "
                "attributes, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(uid) DO UPDATE SET "
                "category = excluded.category, subtype = excluded.subtype, name = excluded.name, commune_code = excluded.commune_code, "
                "lat = excluded.lat, lon = excluded.lon, capacity = COALESCE(excluded.capacity, equipments.capacity), "
                "capacity_unit = CASE WHEN excluded.capacity IS NULL THEN equipments.capacity_unit ELSE excluded.capacity_unit END, "
                "source = excluded.source, attributes = excluded.attributes, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                batch,
            )
        deleted, held = 0, 0
        if replace_source and uids:
            existing = [r["uid"] for r in conn.execute("SELECT uid FROM equipments WHERE source = ?", (source,)).fetchall()]
            stale = set(existing) - set(uids)
            if len(stale) > 10 and len(stale) > MAX_DELETION_SHARE * len(existing):
                held = len(stale)
            else:
                if stale:
                    conn.executemany("DELETE FROM equipments WHERE uid = ?", [(uid,) for uid in stale])
                deleted = len(stale)
    return {"upserted": len(items), "deleted": deleted, "deletion_held": held}


def equipments(commune: Optional[str] = None, categories: Optional[Sequence[str]] = None,
               bbox: Optional[Sequence[float]] = None, statuses: Sequence[str] = STATUSES,
               settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    query = _SELECT + " WHERE 1 = 1"
    params: List[Any] = []
    if bbox:
        west, south, east, north = bbox
        query += f" AND {_EFFECTIVE['lon']} BETWEEN ? AND ? AND {_EFFECTIVE['lat']} BETWEEN ? AND ?"
        params += [west, east, south, north]
    elif commune:
        query += " AND e.commune_code = ?"
        params.append(commune)
    if categories:
        query += f" AND e.category IN ({','.join('?' for _ in categories)})"
        params += list(categories)
    if statuses:
        query += f" AND {_EFFECTIVE['status']} IN ({','.join('?' for _ in statuses)})"
        params += list(statuses)
    with read_db(settings) as conn:
        return [_equipment(r) for r in rows(conn.execute(query + " ORDER BY e.category, e.name", params).fetchall())]


def get_equipment(equipment_id: int, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    with read_db(settings) as conn:
        r = row(conn.execute(_SELECT + " WHERE e.id = ?", (equipment_id,)).fetchone())
    return _equipment(r) if r else None


def save_manual_equipment(data: Dict[str, Any], actor: str, equipment_id: Optional[int] = None,
                          settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Facility entered by the services (existing but missing from open data, provisional, planned)."""
    if data["category"] not in CATEGORIES:
        raise ValueError("Catégorie inconnue")
    if data.get("status", "existant") not in STATUSES:
        raise ValueError("Statut inconnu")
    now = _now()
    with db(settings) as conn:
        if equipment_id is None:
            cur = conn.execute(
                "INSERT INTO equipments (uid, category, subtype, name, commune_code, lat, lon, capacity, capacity_unit, status, source, "
                "attributes, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'saisie', ?, ?, ?) RETURNING id",
                (f"saisie:{now}:{actor}", data["category"], data.get("subtype", ""), data.get("name", ""), data.get("commune"),
                 data["lat"], data["lon"], data.get("capacity"), data.get("capacity_unit", ""), data.get("status", "existant"),
                 json.dumps({"note": data.get("note", "")}), now, actor),
            )
            equipment_id = int(cur.fetchone()[0])
        else:
            existing = conn.execute("SELECT source FROM equipments WHERE id = ?", (equipment_id,)).fetchone()
            if existing is None:
                raise LookupError("Équipement introuvable")
            if existing["source"] != "saisie":
                # Open-data facility: its identity stays the source's; position, capacity, status and note
                # are local corrections kept in equipment_overrides, so a sync never erases them.
                current = conn.execute("SELECT uid, lat, lon, capacity, capacity_unit, status FROM equipments WHERE id = ?",
                                       (equipment_id,)).fetchone()
                moved = abs(float(data["lat"]) - current["lat"]) > 1e-6 or abs(float(data["lon"]) - current["lon"]) > 1e-6
                conn.execute(
                    "INSERT INTO equipment_overrides (uid, lat, lon, capacity, capacity_unit, status, note, updated_at, updated_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(uid) DO UPDATE SET lat = excluded.lat, lon = excluded.lon, "
                    "capacity = excluded.capacity, capacity_unit = excluded.capacity_unit, status = excluded.status, "
                    "note = excluded.note, updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                    (current["uid"], float(data["lat"]) if moved else None, float(data["lon"]) if moved else None,
                     data.get("capacity") if data.get("capacity") != current["capacity"] else None,
                     data.get("capacity_unit") or None,
                     data.get("status") if data.get("status") != current["status"] else None,
                     data.get("note", ""), now, actor),
                )
            else:
                conn.execute(
                    "UPDATE equipments SET category = ?, subtype = ?, name = ?, commune_code = ?, lat = ?, lon = ?, capacity = ?, "
                    "capacity_unit = ?, status = ?, attributes = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                    (data["category"], data.get("subtype", ""), data.get("name", ""), data.get("commune"), data["lat"], data["lon"],
                     data.get("capacity"), data.get("capacity_unit", ""), data.get("status", "existant"),
                     json.dumps({"note": data.get("note", "")}), now, actor, equipment_id),
                )
    out = get_equipment(equipment_id, settings)
    assert out is not None
    return out


def delete_manual_equipment(equipment_id: int, settings: Optional[Settings] = None) -> None:
    with db(settings) as conn:
        r = conn.execute("SELECT source FROM equipments WHERE id = ?", (equipment_id,)).fetchone()
        if r is None:
            raise LookupError("Équipement introuvable")
        if r["source"] != "saisie":
            raise PermissionError("Un équipement issu des données ouvertes ne se supprime pas (il reviendrait à la synchronisation)")
        conn.execute("DELETE FROM equipments WHERE id = ?", (equipment_id,))


def equipment_counts(settings: Optional[Settings] = None) -> Dict[str, Dict[str, int]]:
    with read_db(settings) as conn:
        result = conn.execute("SELECT e.commune_code, e.category, COUNT(*) AS n FROM equipments e "
                              "LEFT JOIN equipment_overrides o ON o.uid = e.uid WHERE COALESCE(o.status, e.status) = 'existant' "
                              "GROUP BY e.commune_code, e.category").fetchall()
    out: Dict[str, Dict[str, int]] = {}
    for r in result:
        out.setdefault(r["commune_code"] or "", {})[r["category"]] = int(r["n"])
    return out
