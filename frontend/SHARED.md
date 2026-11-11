# Socle commun des consoles

Les plateformes de la famille partagent **le même front** (direction
artistique, cadre d'application, composants, écrans transverses) et **le même socle de sécurité**.
Seuls diffèrent le métier (vues, API métier) et l'identité, regroupée dans un seul fichier.

## Fichiers strictement identiques d'un projet à l'autre

| Fichier | Rôle |
| --- | --- |
| `tailwind.config.js` | jetons de design : palette tactique sombre, accent unique `tactical-cyan` (#2dd4bf), couleurs d'état, IBM Plex Sans (interface) / Plex Mono (chiffres, identifiants) |
| `src/main.jsx` | amorçage (charge `index.css` puis `platform.css`) |
| `src/index.css` | polices auto-hébergées, gabarits responsive (`split-view`, `split-pane`, `split-map`, `page`), carte Leaflet, documents signés, impression, focus visible, mouvement réduit |
| `src/components/ui.jsx` | kit d'interface : `Button`, `Panel`, `Pill`, `Field`, `inputClass`, `Spinner`, `Empty`, `ErrorBanner`, `Tabs`, `Modal` |
| `src/components/AppShell.jsx` | `SessionGate` (session, connexion, changement de mot de passe imposé, retour vers /docs/ ou /notifs/) et `AppShell` (bandeau, navigation desktop, tiroir mobile ☰, menu du compte, boîte de changement de mot de passe, garde d'erreur) |
| `src/components/ErrorBoundary.jsx`, `DocLink.jsx`, `Printable.jsx` | erreur isolée par vue, aide contextuelle, impression du seul document (`#print-root`) |
| `src/lib/format.js`, `src/lib/dates.js` | formats (dates dans le fuseau de la plateforme, nombres français), rôles, stockage local sans erreur |
| `src/services/client.js` | transport HTTP (cookie HttpOnly, jeton CSRF, messages d'erreur) et points d'accès communs : authentification, audit, comptes, administration, sources personnalisées |
| `src/views/LoginView.jsx`, `AuditView.jsx`, `UsersTab.jsx`, `CustomSourcesTab.jsx` | écrans transverses |
| `public/fonts/*` | IBM Plex (SIL OFL 1.1), latin + latin étendu |

Côté serveur, `backend/tests/test_shared_core.py` est lui aussi identique : il vérifie le même
socle de sécurité dans chaque API (adresse client derrière le proxy, verrouillage, sonde de
session par rôle, cookie `__Host-`, en-têtes, audit, sources personnalisées, tuiles, nginx).

## Ce qui reste propre à chaque plateforme

| Fichier | Contenu |
| --- | --- |
| `src/platform.js` | identité : nom, accroche, textes de connexion, fuseau d'affichage, délai API, emprise géographique, familles d'actions d'audit, matrice des droits |
| `src/platform.css` | symboles cartographiques du métier |
| `src/App.jsx` | rubriques de navigation, widgets du bandeau (sélecteur de commune / horloges et compteurs), routage des vues |
| `src/services/api.js` | points d'accès métier (ré-exporte `client.js`) |
| `src/theme.js`, `src/views/*` (hors écrans transverses), `src/components/*` (hors socle) | métier |
| `index.html` | seul le `<title>` diffère |

## Règles

1. Une évolution du socle se fait **dans tous les projets à la fois** ; `make shared-check OTHER=../<projet>`
   compare les fichiers ci-dessus avec un projet voisin.
2. Pas de ressource tierce chargée par le navigateur hors des fonds de carte (CSP) : pas de CDN de
   scripts, de styles ni de polices.
3. Toute nouvelle vue reprend les primitives de `ui.jsx` et les gabarits de `index.css` ; sur
   téléphone, une vue carte + panneau empile la carte puis le panneau (`split-view`).
