# Journal d'audit

<p class="where">Bandeau → icône <strong>Audit</strong> — rôle <em>Responsable</em> ou <em>Administrateur</em>.</p>

Chaque action qui compte est inscrite dans un journal **en ajout seul et chaîné** : chaque entrée contient l'empreinte SHA-256 de la précédente. Modifier, supprimer ou déplacer une entrée passée rompt la chaîne, et cela se voit.

## L'écran

- **Bandeau de chaîne** : « Chaîne intègre · n entrées » en vert, ou « CHAÎNE ROMPUE à l'entrée #… » en rouge. La vérification est aussi faite chaque heure, avec une alerte sur **#securite**, et en ligne de commande avec `make verify-audit`.
- **Filtres par famille d'actions** et recherche sur une **partie du nom de l'acteur** (sans tenir compte des majuscules).
- **Colonnes** : numéro, horodatage (heure de Guyane), acteur, action, cible, résultat (`success` / `failure` / `partial`), adresse IP, détails, début de l'empreinte.

## Actions enregistrées

| Famille | Actions |
| --- | --- |
| Connexions | `auth.login`, `auth.logout`, `auth.password_change`, `auth.cli`, `auth.break_glass` |
| Comptes | `user.create`, `user.password_reset` (et les changements de rôle ou d'état) |
| Analyses et données | `analysis.start`, `analysis.done`, `data.sync` |
| Équipements et hypothèses | `equipment.create`, `equipment.update`, `equipment.delete`, `territory.hypothesis` |
| Décision | `decision.siting`, `scenario.save`, `scenario.status`, `scenario.delete` |
| Documents et exports | `report.issue`, `report.verify`, `report.export`, `export.census` |
| Validation et données | `validation.record`, `data.snapshot` (chargement de l'instantané, refus s'il est altéré) |
| Sources personnalisées | `custom_source.create`, `custom_source.update`, `custom_source.delete`, `custom_source.test` |
| Système | `system.settings`, `system.keys`, `system.source_test`, `system.backup`, `system.restore`, `system.factory_reset` |

Les secrets (webhook, mots de passe) ne figurent jamais dans les détails.
