"""Regenerate docs/content/administration/parametres.md from backend/app/services/runtime.py.

Run: make docs-params (in the backend container), or python3 docs/tools/gen_parametres.py
with the backend dependencies installed. A backend test fails when a
runtime setting is missing from the page, so the documentation cannot drift.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
# Backend sources: ../backend in the repository, or BACKEND_DIR (e.g. /app in the container).
sys.path.insert(0, os.environ.get("BACKEND_DIR") or str(DOCS.parent / "backend"))

from app.services.runtime import EDITABLE  # noqa: E402

TYPES = {int: "entier", float: "décimal", bool: "oui / non"}

HEADER = """# Paramètres opérationnels

<p class="where">Administration → <strong>Paramètres</strong> — administrateurs. Page générée depuis le code (<code>docs/tools/gen_parametres.py</code>).</p>

Ces réglages modifient le comportement de la plateforme **sans redémarrage**. Chaque modification est enregistrée, appliquée immédiatement et tracée dans l'audit (`system.settings`). Les **rayons de desserte** traduisent la norme locale de la commune : chaque résultat (atlas, aide à la décision, documents signés) affiche le rayon utilisé.

!!! tip "Méthode"
    Changez **un seul paramètre à la fois** et relancez l'analyse concernée ; les documents déjà émis gardent les valeurs de leur émission.

## Clés API des sources

En tête de l'onglet, la section **Clés API des sources** regroupe les fournisseurs qui demandent une clé. Toutes les sources intégrées fonctionnent **sans clé** : une clé active un **fournisseur de secours**, utilisé seulement quand la source ouverte ne répond pas.

| Fournisseur | Variables | Rôle | Obtenir la clé |
| --- | --- | --- | --- |
| Copernicus Data Space Ecosystem (Sentinel Hub) | `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET` | Catalogue et tuiles couleur Sentinel-2 de l'atlas quand Earth Search (AWS) est injoignable (quota mensuel gratuit) | compte CDSE, puis *User settings → OAuth clients* dans le tableau de bord Sentinel Hub |
| Protected Planet (WDPA) | `PROTECTED_PLANET_TOKEN` | Aires protégées (contrainte d'implantation) quand le serveur UNEP-WCMC ne répond pas | demande de jeton sur api.protectedplanet.net |

- **Enregistrer** chiffre la valeur dans le coffre (`keys/api_credentials.enc`, clé maître hors sauvegardes) et l'applique sans redémarrage ; elle remplace la valeur du fichier `.env`.
- La valeur n'est **jamais renvoyée** au navigateur : seuls l'origine (coffre ou `.env`) et les 4 derniers caractères sont affichés.
- **Tester** vérifie la clé en direct (jeton et recherche de scènes pour Copernicus, lecture des aires protégées de Guyane pour Protected Planet).
- **Supprimer** retire la valeur du coffre et rétablit celle du `.env`, s'il y en a une.
- Chaque modification est tracée dans l'audit (`system.keys`) et notifiée sur le canal #securite.

Pour une autre API à clé (WMS sous licence, API métier…), déclarez une [source personnalisée](sources-personnalisees.md) : son secret est chiffré de la même façon.

## Vue d'ensemble

| Paramètre | Valeur par défaut | Plage | Unité |
| --- | --- | --- | --- |
"""


def main() -> None:
    lines = [HEADER]
    for key, (typ, low, high, label, meta) in EDITABLE.items():
        lines.append(f"| [{label}](#{key.replace('_', '-')}) | {meta['default']} | {low} – {high} | {meta['unit']} |\n")
    for key, (typ, low, high, label, meta) in EDITABLE.items():
        lines.append(f"\n## {label} {{#{key.replace('_', '-')}}}\n\n")
        lines.append(f"Nom technique : `{key}` · type {TYPES.get(typ, typ.__name__)} · plage {low} – {high} {meta['unit']} · "
                     f"défaut **{meta['default']}**\n\n")
        lines.append(f"{meta['what']}\n\n")
        if meta.get("higher"):
            lines.append(f"- **▲ Augmenter** : {meta['higher']}\n")
        if meta.get("lower"):
            lines.append(f"- **▼ Diminuer** : {meta['lower']}\n\n")
        lines.append(f"!!! success \"Recommandation\"\n    {meta['advice']}\n")
    out = DOCS / "content" / "administration" / "parametres.md"
    out.write_text("".join(lines), encoding="utf-8")
    print(f"{out} ({len(EDITABLE)} paramètres)")


if __name__ == "__main__":
    main()
