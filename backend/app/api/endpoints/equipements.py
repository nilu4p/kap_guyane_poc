"""Public facilities and everyday services: open data + entries by the services."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import analyst, viewer
from app.core import audit
from app.territoire import store

router = APIRouter(prefix="/equipements", tags=["equipements"])


class Equipment(BaseModel):
    category: str = Field(..., max_length=40)
    subtype: str = Field("", max_length=80)
    name: str = Field("", max_length=200)
    commune: Optional[str] = Field(None, pattern=r"^\d{5}$")
    lat: float = Field(..., ge=1.5, le=6.5)
    lon: float = Field(..., ge=-55.5, le=-51.0)
    capacity: Optional[float] = Field(None, ge=0, le=1_000_000)
    capacity_unit: str = Field("", max_length=60)
    status: str = Field("existant", max_length=20)
    note: str = Field("", max_length=1000)


@router.get("/categories")
def categories(_user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    from app.config import get_settings

    cfg = get_settings()
    return {"categories": [{"id": k, **v, "radius_m": cfg.coverage_radii_m.get(k)} for k, v in store.CATEGORIES.items()],
            "statuses": list(store.STATUSES)}


@router.get("")
def list_equipments(commune: Optional[str] = Query(None, pattern=r"^\d{5}$"),
                    category: Optional[List[str]] = Query(None),
                    _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    items = store.equipments(commune=commune, categories=category)
    return {"equipments": items, "count": len(items)}


@router.post("")
def create_equipment(body: Equipment, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    try:
        item = store.save_manual_equipment(body.model_dump(), user["username"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record("equipment.create", actor=user["username"], target=f"equipment:{item['id']}",
                 details={"category": item["category"], "status": item["status"], "commune": item["commune_code"]})
    return {"equipment": item}


@router.put("/{equipment_id}")
def update_equipment(equipment_id: int, body: Equipment, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    try:
        item = store.save_manual_equipment(body.model_dump(), user["username"], equipment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record("equipment.update", actor=user["username"], target=f"equipment:{equipment_id}",
                 details={"status": item["status"], "capacity": item["capacity"]})
    return {"equipment": item}


@router.delete("/{equipment_id}")
def delete_equipment(equipment_id: int, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    try:
        store.delete_manual_equipment(equipment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit.record("equipment.delete", actor=user["username"], target=f"equipment:{equipment_id}")
    return {"deleted": equipment_id}
