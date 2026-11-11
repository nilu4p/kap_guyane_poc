"""The knowledge base (docs/content) must follow the code: settings, channels, API, KPIs."""

from __future__ import annotations

from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs" / "content"
pytestmark = pytest.mark.skipif(not DOCS.is_dir(), reason="documentation sources not present (backend image)")


def _read(page: str) -> str:
    return (DOCS / page).read_text(encoding="utf-8")


def test_every_runtime_setting_is_documented() -> None:
    from app.services.runtime import EDITABLE

    page = _read("administration/parametres.md")
    missing = [name for name in EDITABLE if f"`{name}`" not in page]
    assert not missing, f"make docs-params : paramètres absents de la documentation : {missing}"


def test_every_notification_channel_is_documented() -> None:
    from app.services.notify import CHANNELS

    page = _read("administration/notifications.md")
    assert all(f"`#{c}`" in page for c in CHANNELS)


def test_every_api_domain_is_documented() -> None:
    from app.api.router import api_router

    page = _read("api.md")
    paths = [getattr(route, "path", "") for route in api_router.routes]
    prefixes = {p.split("/")[3] for p in paths if p.count("/") >= 3}
    missing = [p for p in prefixes if f"/{p}" not in page]
    assert not missing, f"domaines d'API absents de docs/content/api.md : {missing}"


def test_every_kpi_family_is_documented() -> None:
    from app.territoire.profile import THEMES

    page = _read("methodes/indicateurs.md")
    assert all(label.split(" ")[0] in page for label in THEMES.values())
