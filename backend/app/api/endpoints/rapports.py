"""Signed decision documents: drafts, issue, register, verification, export."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import analyst, supervisor, viewer
from app.services import reports

router = APIRouter(prefix="/rapports", tags=["rapports"])


class DraftBody(BaseModel):
    kind: str
    commune: Optional[str] = Field(None, pattern=r"^\d{5}$")
    scenario_id: Optional[int] = None
    since: int = Field(2019, ge=1985, le=2100)
    assessment: str = Field("", max_length=8000)
    proposals: str = Field("", max_length=8000)
    addressees: str = Field("", max_length=600)


def _draft(body: DraftBody, user: Dict[str, Any], issue: bool) -> Dict[str, Any]:
    try:
        return reports.draft(body.kind, user, commune=body.commune, scenario_id=body.scenario_id, since=body.since,
                             assessment=body.assessment, proposals=body.proposals, addressees=body.addressees, issue=issue)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except reports.ReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
def list_reports(commune: Optional[str] = Query(None, pattern=r"^\d{5}$"), _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    return {"reports": reports.list_reports(commune=commune), "kinds": reports.KINDS}


@router.post("/projet")
def draft_report(body: DraftBody, user: Dict[str, Any] = Depends(analyst)) -> Dict[str, Any]:
    """Preview: nothing is stored."""
    return _draft(body, user, issue=False)


@router.post("/emettre")
def issue_report(body: DraftBody, user: Dict[str, Any] = Depends(supervisor)) -> Dict[str, Any]:
    """Freeze, hash, sign and register the document (head of department)."""
    return _draft(body, user, issue=True)


@router.get("/certificat")
def certificate(_user: Dict[str, Any] = Depends(viewer)) -> Response:
    """Root certificate of this instance (PEM) and its fingerprint: lets a recipient check a signed
    document outside the platform (openssl, or any X.509 / ECDSA tool)."""
    from app.config import get_settings
    from app.core import pki

    cfg = get_settings()
    pki.ensure_pki(cfg)
    pem = pki.trusted_roots_pem(cfg)
    return Response(content=pem.encode("ascii"), media_type="application/x-pem-file",
                    headers={"Content-Disposition": 'attachment; filename="kap-guyane-racine.pem"',
                             "X-Root-Fingerprint-SHA256": pki.root_fingerprint_sha256(cfg)})


@router.get("/{report_id}")
def get_report(report_id: int, _user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    report = reports.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Document introuvable")
    report.pop("certificate", None)
    return {"report": report}


@router.post("/{report_id}/verifier")
def verify_report(report_id: int, user: Dict[str, Any] = Depends(viewer)) -> Dict[str, Any]:
    try:
        return reports.verify(report_id, user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{report_id}/export")
def export_report(report_id: int, user: Dict[str, Any] = Depends(viewer)) -> Response:
    try:
        name, text = reports.export_text(report_id, user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=text.encode("utf-8"), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
