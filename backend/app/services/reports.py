"""Signed decision documents: commune diagnosis, siting file, census scout list.

A document is drafted from the platform's records (statistics, satellite analysis,
scenario), completed by the author (assessment, proposals, addressees), then
**issued** by a head of department: its text is frozen, hashed (SHA-256) and
signed with the instance PKI (ECDSA), stored in the register and in the audit
trail. Verification recomputes the hash, checks the signature with the stored
certificate and that this certificate chains to a root of this instance — so a
figure quoted in a council meeting can be traced back to what was computed.

Every document carries the hypotheses and the ethics notice it relies on.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config import Settings, get_settings
from app.core import audit
from app.db import db, read_db, row, rows

logger = logging.getLogger(__name__)

KINDS = {"diagnostic": "Diagnostic de commune", "implantation": "Dossier d'aide à l'implantation",
         "recensement": "Liste « Recensement Éclaireur » (appui au RIL)"}
PREFIXES = {"diagnostic": "DIAG", "implantation": "IMPL", "recensement": "RIL"}
WIDTH = 96
ETHICS = ("Outil de planification, pas de contrôle : données agrégées par carreaux de 200 m, aucune construction "
          "individuelle désignée, aucune distinction légal / illégal. Usage fiscal, de contrôle ou d'expulsion exclu "
          "(charte d'usage KAP Guyane, décisions du Défenseur des droits 2023-31 et 2025-102).")

Section = Dict[str, Any]


class ReportError(ValueError):
    pass


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _fmt(value: Any, decimals: int = 0) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        text = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
        return text
    return str(value)


def render_text(header: Dict[str, Any], sections: Sequence[Section]) -> str:
    """Canonical document text (what is hashed and signed)."""
    rule = "-" * WIDTH
    lines = [header["classification"], rule, header["title"].upper()]
    for label, value in (("RÉF.", header["ref"]), ("DATE", header["date"]), ("ORIGINE", header["originator"]),
                         ("RÉDACTEUR", header["author"]), ("DESTINATAIRES", header["addressees"] or "—"),
                         ("OBJET", header["subject"])):
        lines.extend(textwrap.wrap(f"{label:<14}: {value}", WIDTH, break_on_hyphens=False, subsequent_indent=" " * 16) or [label])
    lines.append(rule)
    for number, section in enumerate(sections, start=1):
        lines.append("")
        lines.append(f"{number}. {section['title'].upper()}")
        for label, value in section.get("rows") or []:
            lines.extend(textwrap.wrap(f"   {label} : {value}", WIDTH, break_on_hyphens=False, subsequent_indent="      ") or [""])
        for paragraph in section.get("paragraphs") or []:
            lines.extend(textwrap.wrap(paragraph, WIDTH, break_on_hyphens=False, initial_indent="   ", subsequent_indent="   ") or [""])
        table = section.get("table")
        if table and table.get("rows"):
            columns = table["columns"]
            for record in table["rows"]:
                text = " | ".join(f"{c}: {v}" for c, v in zip(columns, record) if v not in (None, ""))
                lines.extend(textwrap.wrap(f"   - {text}", WIDTH, break_on_hyphens=False, subsequent_indent="     "))
        elif table:
            lines.append(f"   {table.get('empty') or 'Néant.'}")
    lines.extend(["", rule, header["classification"]])
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- signature


def _sign(content: bytes, cfg: Settings) -> Tuple[str, str, str]:
    """(signature b64, certificate PEM, certificate SHA-256) — empty strings when no PKI is available."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        from app.core import pki

        pki.ensure_pki(cfg)
        key = serialization.load_pem_private_key(pki.signing_key_pem(cfg), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            return "", "", ""
        signature = key.sign(content, ec.ECDSA(hashes.SHA256()))
        certificate = (Path(cfg.keys_dir) / "cert.pem").read_text(encoding="ascii")
        return base64.b64encode(signature).decode(), certificate, pki.leaf_fingerprint_sha256(cfg)
    except Exception:  # an unsigned document is still issued (hash + audit), and says so
        logger.exception("Report signature unavailable")
        return "", "", ""


def verify(report_id: int, user: Dict[str, Any], settings: Optional[Settings] = None) -> Dict[str, Any]:
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec

    from app.core import pki

    cfg = settings or get_settings()
    report = get_report(report_id, cfg)
    if report is None:
        raise LookupError("Document introuvable")
    content = report["content"].encode("utf-8")
    hash_ok = hashlib.sha256(content).hexdigest() == report["sha256"]
    signature_ok: Optional[bool] = None
    chain_ok: Optional[bool] = None
    if report["signature"] and report["certificate"]:
        cert = None
        try:
            cert = x509.load_pem_x509_certificate(report["certificate"].encode("ascii"))
            cert.public_key().verify(base64.b64decode(report["signature"]), content, ec.ECDSA(hashes.SHA256()))  # type: ignore[call-arg]
            signature_ok = True
        except (InvalidSignature, ValueError):
            signature_ok = False
        chain_ok = False
        if cert is not None:
            for root in pki.trusted_roots(cfg):
                try:
                    root.public_key().verify(cert.signature, cert.tbs_certificate_bytes,  # type: ignore[call-arg]
                                             ec.ECDSA(cert.signature_hash_algorithm))  # type: ignore[arg-type]
                    chain_ok = True
                    break
                except Exception:
                    continue
    valid = hash_ok and signature_ok is not False and chain_ok is not False
    audit.record("report.verify", actor=user["username"], target=f"report:{report['ref']}",
                 outcome="success" if valid else "failure",
                 details={"hash": hash_ok, "signature": signature_ok, "chain": chain_ok}, settings=cfg)
    return {"ref": report["ref"], "valid": valid, "hash_ok": hash_ok, "signature_ok": signature_ok, "chain_ok": chain_ok,
            "signed": bool(report["signature"]), "sha256": report["sha256"], "cert_fingerprint": report["cert_fingerprint"]}


# --------------------------------------------------------------------------- sections


def _text_sections(assessment: str, proposals: str) -> List[Section]:
    out = []
    if assessment.strip():
        out.append({"title": "Appréciation des services", "paragraphs": [p for p in assessment.strip().split("\n") if p.strip()]})
    if proposals.strip():
        out.append({"title": "Propositions", "paragraphs": [p for p in proposals.strip().split("\n") if p.strip()]})
    return out


def diagnostic_sections(commune: str, cfg: Settings) -> Tuple[str, List[Section]]:
    from app.analyse import population, watch
    from app.territoire import profile

    prof = profile.profile(commune, cfg)
    if prof is None:
        raise LookupError("Commune inconnue")
    c = prof["commune"]
    sections: List[Section] = [{"title": "Commune", "rows": [
        ["Commune", f"{c['nom']} ({c['code']})"], ["Intercommunalité", c.get("epci") or "—"],
        ["Superficie", f"{_fmt((c.get('surface_ha') or 0) / 100, 0)} km²"],
    ]}]
    hyp = prof.get("hypothesis")
    for theme in prof["themes"]:
        records = [[k["label"], f"{_fmt(k['value'], k['decimals'])} {k['unit']}", str(k["year"] or "—"),
                    _fmt(k["guyane"], k["decimals"]) if k["guyane"] is not None else "—",
                    f"{k['rank']}/{k['ranked']}" if k["rank"] else "—"]
                   for k in theme["kpis"] if k["value"] is not None]
        sections.append({"title": theme["label"], "table": {"columns": ["Indicateur", "Valeur", "Année", "Guyane", "Rang"],
                                                            "rows": records, "empty": "Aucune donnée disponible."}})
    if hyp:
        sections.append({"title": "Hypothèse de population de la commune", "rows": [
            ["Valeur", f"{_fmt(hyp['value'])} habitants ({hyp['year']})"],
            ["Fourchette", f"{_fmt(hyp.get('low'))} – {_fmt(hyp.get('high'))}" if hyp.get("low") else "—"],
            ["Source déclarée", hyp.get("source") or "—"]],
            "paragraphs": ["Cette hypothèse n'est pas un chiffre officiel ; elle est affichée à côté de la population légale INSEE."]})
    totals = population.totals_by_year(commune, cfg)
    if totals.get("available"):
        from app.analyse import builtup, satellite

        quality = satellite.grade((builtup.load(commune, cfg) or {}).get("meta", {}).get("calibration"))
        series = totals["series"]
        last = series[-1]
        sections.append({"title": "Croissance du bâti mesurée par satellite", "rows": [
            ["Surface bâtie 2019 (WSF 2019)", f"{_fmt(next((s['built_ha'] for s in series if s['year'] == 2019), None), 1)} ha"],
            [f"Surface bâtie {last['year']}", f"{_fmt(last['built_ha'], 1)} ha"],
            ["Population que le bâti pourrait loger (occupation constante)", f"{_fmt(last['model'])} habitants"],
            ["Densité calibrée", f"{_fmt(totals['density_per_built_ha'], 1)} hab. par hectare bâti"],
            ["Qualité de la série Sentinel-2", f"{quality['level']} — {quality['label']}"],
        ], "paragraphs": ["Indicateur indépendant et reproductible (WSF 2019, Sentinel-2) : ce n'est pas un contre-recensement.",
                          quality["advice"]]})
        hot = watch.hotspots(commune, cfg, notify=False)
        if hot.get("clusters"):
            sections.append({"title": "Quartiers en croissance", "table": {
                "columns": ["Repère", "Bâti gagné", "Habitants estimés", "École la plus proche"],
                "rows": [[cl.get("landmark") or f"{cl['lat']}, {cl['lon']}", f"+{_fmt(cl['growth_ha'], 1)} ha",
                          _fmt(cl["new_inhabitants"]),
                          f"{_fmt((cl['nearest'].get('ecole') or {}).get('distance_m'))} m" if cl["nearest"].get("ecole") else "—"]
                         for cl in hot["clusters"][:10]]}})
    sections.append({"title": "Sources et limites", "paragraphs": prof["notes"] + [ETHICS]})
    return f"Diagnostic territorial — {c['nom']}", sections


def implantation_sections(scenario: Dict[str, Any], cfg: Settings) -> Tuple[str, List[Section]]:
    from app.analyse import access
    from app.territoire import store

    commune = store.commune(scenario["commune_code"], cfg)
    if commune is None:
        raise LookupError("Commune inconnue")
    label = store.CATEGORIES[scenario["category"]]["label"]
    stored = scenario.get("evaluation") or {}
    if scenario.get("status") == "valide" and stored.get("frozen_at"):
        evaluation = stored  # figures frozen at validation: the document quotes what was decided
        basis = (f"Chiffres figés à la validation du {str(stored['frozen_at'])[:10]} par {stored.get('frozen_by')} "
                 f"(analyse du bâti du {str((stored.get('basis') or {}).get('analysis_computed_at') or '—')[:10]}).")
    else:
        evaluation = access.evaluate(scenario["commune_code"], scenario["category"], scenario["sites"], settings=cfg,
                                     use_hypothesis=bool((scenario.get("params") or {}).get("use_hypothesis")))
        basis = "Scénario non validé : chiffres recalculés sur les données du jour."
    if not evaluation.get("available"):
        raise ReportError(evaluation.get("reason") or "Évaluation impossible")
    b, a = evaluation["before"], evaluation["after"]
    sections: List[Section] = [
        {"title": "Objet", "rows": [["Commune", f"{commune['nom']} ({commune['code']})"], ["Équipement", label],
                                     ["Scénario", scenario["name"]], ["Statut", scenario.get("status", "brouillon")]],
         "paragraphs": [scenario.get("description") or ""] if scenario.get("description") else []},
        {"title": "Effet attendu sur la desserte", "rows": [
            ["Rayon de desserte", f"{_fmt(evaluation['radius_m'])} m de trajet estimé (vol d'oiseau × facteur de détour)"],
            ["Demande desservie avant (avec une place pour les écoles)", f"{_fmt(b['demand_covered'])} / {_fmt(b['demand_total'])} ({_fmt((b['coverage_rate'] or 0) * 100, 1)} %)"],
            ["Demande desservie après", f"{_fmt(a['demand_covered'])} / {_fmt(a['demand_total'])} ({_fmt((a['coverage_rate'] or 0) * 100, 1)} %)"],
            ["Gain", f"+{_fmt(evaluation['gain']['demand'])} ({'enfants' if store.CATEGORIES[scenario['category']]['demand'] != 'pop' else 'habitants'})"],
            ["Distance moyenne avant / après", f"{_fmt(b['mean_distance_m'])} m / {_fmt(a['mean_distance_m'])} m"],
        ]},
        {"title": "Sites", "table": {"columns": ["Site", "Position", "Demande rattachée", "Capacité"], "rows": [
            [s.get("name") or f"Site {n}", f"{s['lat']:.5f}, {s['lon']:.5f}", _fmt(s.get("catchment_demand")),
             _fmt(s.get("capacity")) if s.get("capacity") else "—"] for n, s in enumerate(evaluation["sites"], start=1)]}},
        {"title": "Hypothèses", "paragraphs": [
            basis,
            evaluation["population"]["method"],
            f"Base : {evaluation['population']['calibration']['basis']} ; densité {_fmt(evaluation['population']['density_per_built_ha'], 1)} "
            "habitants par hectare bâti.",
            "Foncier, risques naturels (PPRI), réseaux et accès réels sont à vérifier sur le terrain : la plateforme ne les connaît pas.",
        ]},
        {"title": "Charte d'usage", "paragraphs": [ETHICS]},
    ]
    return f"Implantation — {label} — {commune['nom']}", sections


def recensement_sections(commune_code: str, since: int, cfg: Settings) -> Tuple[str, List[Section]]:
    from app.analyse import watch
    from app.territoire import store

    commune = store.commune(commune_code, cfg)
    if commune is None:
        raise LookupError("Commune inconnue")
    scout = watch.census_scout(commune_code, since, cfg)
    if not scout.get("available"):
        raise ReportError("Analyse du bâti non réalisée pour cette commune")
    sections: List[Section] = [
        {"title": "Objet", "paragraphs": [
            f"Carreaux de 200 m où la surface bâtie a augmenté entre {scout['since']} et {scout['until']}, à transmettre à "
            "l'INSEE avant la collecte de janvier pour vérification du répertoire d'immeubles localisés (RIL)."]},
        {"title": "Carreaux signalés", "table": {
            "columns": ["Carreau", "Centre (lat, lon)", "Bâti gagné", "Bâtiments estimés"],
            "rows": [[r["cell"], f"{r['lat']}, {r['lon']}", f"+{_fmt(r['growth_ha'], 2)} ha", _fmt(r["new_buildings_est"])]
                     for r in scout["rows"]], "empty": "Aucun carreau au-dessus du seuil."}},
        {"title": "Règle de secret", "rows": [["Carreaux non listés", str(scout["hidden"]["cells"])],
                                               ["Bâti gagné non listé", f"{_fmt(scout['hidden']['growth_ha'], 2)} ha"],
                                               ["Règle", scout["hidden"]["rule"]]]},
        {"title": "Charte d'usage", "paragraphs": [scout["notice"], ETHICS]},
    ]
    return f"Recensement Éclaireur — {commune['nom']} ({scout['since']} → {scout['until']})", sections


# --------------------------------------------------------------------------- issue / draft


def _issue(kind: str, *, title: str, subject: str, sections: List[Section], user: Dict[str, Any], addressees: str,
           cfg: Settings, commune: Optional[str], scenario_id: Optional[int]) -> Dict[str, Any]:
    now = _now()
    author = f"{user.get('display_name') or user['username']} ({user['username']})"
    with db(cfg) as conn:
        report_id = conn.execute(
            "INSERT INTO reports (ref, kind, commune_code, scenario_id, title, classification, created_at, created_by, content, "
            "sections, sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '[]', '') RETURNING id",
            (f"pending-{now.timestamp()}-{user['username']}"[:120], kind, commune, scenario_id, title,
             cfg.report_classification, now.isoformat(), user["username"]),
        ).fetchone()[0]
        ref = f"{PREFIXES[kind]}-{now.year}-{report_id:04d}"
        header = {"classification": cfg.report_classification, "title": KINDS[kind], "ref": ref,
                  "date": now.strftime("%d/%m/%Y %H:%M UTC"), "originator": cfg.report_originator, "author": author,
                  "addressees": addressees.strip(), "subject": subject}
        content = render_text(header, sections)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        signature, certificate, fingerprint = _sign(content.encode("utf-8"), cfg)
        conn.execute(
            "UPDATE reports SET ref = ?, content = ?, sections = ?, sha256 = ?, signature = ?, certificate = ?, "
            "cert_fingerprint = ? WHERE id = ?",
            (ref, content, json.dumps({"header": header, "sections": sections}, ensure_ascii=False, default=str),
             digest, signature, certificate, fingerprint, report_id),
        )
    audit.record("report.issue", actor=user["username"], target=f"report:{ref}",
                 details={"kind": kind, "sha256": digest, "signed": bool(signature), "commune": commune}, settings=cfg)
    from app.services import notify

    notify.notify_event("decisions", f"Document signé émis — {ref}", level="info",
                        details={"Document": KINDS[kind], "Objet": subject, "Par": author}, view="rapports", label="Registre",
                        settings=cfg)
    return get_report(report_id, cfg)  # type: ignore[return-value]


def draft(kind: str, user: Dict[str, Any], *, commune: Optional[str] = None, scenario_id: Optional[int] = None,
          since: int = 2019, assessment: str = "", proposals: str = "", addressees: str = "", issue: bool = False,
          settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Preview (``issue=False``: nothing stored) or issue a decision document."""
    cfg = settings or get_settings()
    if kind not in KINDS:
        raise ReportError("Type de document inconnu")
    if kind == "implantation":
        from app.services import scenarios

        scenario = scenarios.get(scenario_id or 0, cfg)
        if scenario is None:
            raise LookupError("Scénario introuvable")
        commune = scenario["commune_code"]
        subject, sections = implantation_sections(scenario, cfg)
    elif kind == "diagnostic":
        subject, sections = diagnostic_sections(commune or "", cfg)
    else:
        subject, sections = recensement_sections(commune or "", since, cfg)
    sections = sections[:1] + _text_sections(assessment, proposals) + sections[1:]
    if issue:
        return _issue(kind, title=f"{KINDS[kind]} — {subject}", subject=subject, sections=sections, user=user,
                      addressees=addressees, cfg=cfg, commune=commune, scenario_id=scenario_id)
    header = {"classification": cfg.report_classification, "title": KINDS[kind], "ref": "(projet — non émis)",
              "date": _now().strftime("%d/%m/%Y %H:%M UTC"), "originator": cfg.report_originator,
              "author": f"{user.get('display_name') or user['username']} ({user['username']})",
              "addressees": addressees.strip(), "subject": subject}
    return {"draft": True, "kind": kind, "header": header, "sections": sections, "content": render_text(header, sections)}


def _decorate(report: Dict[str, Any], full: bool) -> Dict[str, Any]:
    report["kind_label"] = KINDS.get(report["kind"], report["kind"])
    report["signed"] = bool(report.get("signature"))
    if full:
        structured = json.loads(report.pop("sections") or "{}") or {}
        report["header"] = structured.get("header")
        report["sections"] = structured.get("sections") or []
    else:
        for heavy in ("content", "sections", "signature", "certificate"):
            report.pop(heavy, None)
    return report


def list_reports(*, commune: Optional[str] = None, kind: Optional[str] = None, limit: int = 200,
                 settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    clauses, params = [], []
    if commune:
        clauses.append("commune_code = ?")
        params.append(commune)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with read_db(settings) as conn:
        result = rows(conn.execute(f"SELECT * FROM reports {where} ORDER BY created_at DESC, id DESC LIMIT ?",
                                   (*params, limit)).fetchall())
    return [_decorate(r, full=False) for r in result]


def get_report(report_id: int, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    with read_db(settings) as conn:
        report = row(conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone())
    return _decorate(report, full=True) if report else None


def _root_fingerprint(cfg: Settings) -> str:
    try:
        from app.core import pki

        return pki.root_fingerprint_sha256(cfg)
    except Exception:
        return "—"


def export_text(report_id: int, user: Dict[str, Any], settings: Optional[Settings] = None) -> Tuple[str, str]:
    """(file name, text): the signed document followed by its seal block (hash, signature, certificate)."""
    cfg = settings or get_settings()
    report = get_report(report_id, cfg)
    if report is None:
        raise LookupError("Document introuvable")
    seal = [
        "=" * WIDTH,
        "SCELLEMENT KAP Guyane — le texte signé est exactement tout ce qui précède la ligne de « = » ci-dessus",
        f"SHA-256          : {report['sha256']}",
        f"Signature ECDSA  : {report['signature'] or 'non signé (PKI indisponible à l’émission)'}",
        f"Certificat (SHA-256) : {report['cert_fingerprint'] or '—'}",
        f"Racine de confiance (SHA-256) : {_root_fingerprint(cfg)}",
        "Vérification hors plateforme : extraire le certificat ci-dessous et la racine (Rapports › Certificat racine),",
        "  openssl verify -CAfile racine.pem cert.pem ; puis vérifier la signature ECDSA-SHA256 du texte avec la clé publique du certificat.",
        "Horodatage : horloge du serveur (pas d'autorité d'horodatage RFC 3161 configurée).",
    ]
    if report["certificate"]:
        seal += ["", report["certificate"].strip()]
    audit.record("report.export", actor=user["username"], target=f"report:{report['ref']}", settings=cfg)
    return f"{report['ref']}.txt", report["content"] + "\n".join(seal) + "\n"
