"""Satellite imagery served by the platform: Sentinel-2 10 m true colour over a commune."""

from __future__ import annotations

import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.api.deps import viewer
from app.sources import sentinel2
from app.territoire import store

router = APIRouter(prefix="/imagery", tags=["imagery"])

# Yearly cloudless Sentinel-2 mosaics published by EOX (s2maps.eu): background of the time slider.
EOX_YEARS = (2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)


@router.get("/layers")
def imagery_layers(_user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    """Background mosaics available for the time slider (tiles served directly by EOX)."""
    return {"eox": [{"year": y, "layer": f"s2cloudless-{y}_3857" if y != 2016 else "s2cloudless_3857",
                     "licence": "CC BY 4.0" if y == 2016 else "CC BY-NC-SA 4.0",
                     "attribution": f"Sentinel-2 cloudless {y} by EOX IT Services GmbH (contient des données Copernicus Sentinel modifiées)"}
                    for y in EOX_YEARS]}


@router.get("/sentinel2/scenes")
def sentinel2_scenes(
    commune: str = Query(..., pattern=r"^\d{5}$"),
    days: int = Query(90, ge=5, le=365),
    max_cloud: float = Query(30, ge=0, le=100),
    _user: Dict[str, Any] = Depends(viewer),
) -> Dict[str, Any]:
    """Clearest Sentinel-2 scene per tile over a commune in the last ``days`` days."""
    c = store.commune(commune)
    if c is None:
        raise HTTPException(status_code=404, detail="Commune inconnue")
    now = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
    return sentinel2.scenes(c["bbox"], now, days=days, max_cloud=max_cloud, clearest=True)


@router.get("/sentinel2/tiles/{item_id}/{z}/{x}/{y}.png")
async def sentinel2_tile(
    item_id: str = Path(..., max_length=40, pattern=r"^S2[ABC]_[0-9]{2}[A-Z]{3}_[0-9]{8}_[0-9]+_L2A$"),
    z: int = Path(..., ge=sentinel2.MIN_ZOOM, le=sentinel2.MAX_ZOOM),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
    _user: Dict[str, Any] = Depends(viewer),
) -> Response:
    """One Web-Mercator map tile of a scene (PNG, transparent outside the image)."""
    try:
        data = await run_in_threadpool(sentinel2.render_tile, item_id, z, x, y)
    except sentinel2.Sentinel2Error as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
