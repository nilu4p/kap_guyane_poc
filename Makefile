# KAP Guyane — commandes d'exploitation.
# `make` (ou `make help`) affiche cette aide, générée à partir des commentaires `##`
# placés au-dessus de chaque cible et des sections `##@`.

.DEFAULT_GOAL := help
.PHONY: help up down restart status build logs docs docs-params secrets psql workers test-pg dev dev-backend dev-frontend test \
        sync analyse snapshot \
        admin admin-password user users reset-password \
        backup backups-list reset restore \
        verify-audit master-key notifs venv shared-check

# Optional local virtualenv (make venv) for development outside Docker.
VENV := $(CURDIR)/.venv
VENV_PYTHON := $(VENV)/bin/python
HAS_VENV := $(wildcard $(VENV_PYTHON))
COMPOSE := docker compose
# Containers write keys/, cache/, data/… as this UID: it must own those folders on the host
# (the first user of a cloud VM is often 1001, not 1000).
export APP_UID ?= $(shell id -u)
RUN_CLI := $(COMPOSE) run --rm backend python main.py
# Services that write to the database (stopped during reset and restore).
APP_SERVICES := backend worker worker-analysis beat console
RECOVERY_FLAG = $(if $(RECOVERY),--recovery,)
# Addresses printed after `make up`.
CONSOLE_URL = https://$(or $(shell sed -n 's/^DOMAIN=//p' .env 2>/dev/null),localhost)
UP_BANNER = echo "Console : $(CONSOLE_URL) · Documentation : $(CONSOLE_URL)/docs/ · Notifications : $(CONSOLE_URL)/notifs/"; \
	echo "Premier mot de passe admin : make admin-password · Nouvel admin : make admin"
# CLI exit codes: 0 ok · 10 cancelled by the operator (not an error) · 3 authentication
# refused · other = failure. Cancellation must not end with a make "Error".
cli_exit = case $(1) in 0|10) exit 0 ;; 3) echo "Authentification refusée : aucune modification."; exit 3 ;; \
	*) echo "Échec (code $(1)) : voir le message ci-dessus."; exit $(1) ;; esac

##@ Aide

## Affiche cette aide : toutes les commandes, ce qu'elles font et leurs options.
help:
	@awk ' \
	BEGIN { bold = "\033[1m"; cyan = "\033[36m"; dim = "\033[2m"; reset = "\033[0m"; \
	        printf "\n%sKAP Guyane — GEOINT et aide à la décision territoriale%s\n", bold, reset; \
	        printf "%sUsage : make <commande> [VARIABLE=valeur]%s\n", dim, reset } \
	/^##@/ { printf "\n%s%s%s\n", bold, substr($$0, 5), reset; desc = ""; next } \
	/^## / { desc = desc "\n" substr($$0, 4); next } \
	/^[a-zA-Z0-9_-]+:/ && desc != "" { \
	        split($$0, parts, ":"); n = split(desc, lines, "\n"); \
	        printf "  %s%-16s%s %s\n", cyan, parts[1], reset, lines[2]; \
	        for (i = 3; i <= n; i++) printf "  %-16s %s%s%s\n", "", dim, lines[i], reset; \
	        desc = ""; next } \
	{ desc = "" }' $(MAKEFILE_LIST)
	@printf "\n"

##@ Démarrage et exploitation courante

## Construit les images si besoin et démarre toute la plateforme en arrière-plan :
## backend (API, 127.0.0.1:8000), console (https://localhost, ou https://$DOMAIN),
## documentation (/docs/) et serveur de notifications PoC (/notifs/).
## Premier démarrage : mot de passe admin avec `make admin-password`. Les statistiques,
## les équipements et les analyses embarquées (instantané hors ligne) sont chargés
## automatiquement ; `make sync` les met à jour depuis les sources ouvertes.
## Architecture : PostgreSQL, Redis, workers Celery (analyses, notifications), planificateur.
up: secrets
	mkdir -p keys cache data backups
	$(COMPOSE) up -d --build --remove-orphans
	@$(UP_BANNER)

## Génère (une seule fois) les mots de passe PostgreSQL et Redis et la clé maître dans
## secrets/ (dossier 700, jamais versionné, hors sauvegardes). Une ancienne
## keys/master.key y est déplacée (les secrets déjà chiffrés restent lisibles).
## Appelé automatiquement par `make up`.
## Fichiers en 644 : les conteneurs (postgres, redis, backend) tournent sous des UID
## différents et lisent le secret monté tel quel ; c'est le dossier 700 qui le protège
## des autres comptes de la machine.
secrets:
	@mkdir -p secrets && chmod 700 secrets
	@for name in postgres_password redis_password; do \
	  if [ ! -s secrets/$$name ]; then \
	    python3 -c "import secrets; print(secrets.token_urlsafe(32))" > secrets/$$name; \
	    chmod 644 secrets/$$name; echo "Secret généré : secrets/$$name"; \
	  fi; \
	done
	@if [ ! -s secrets/master_key ]; then \
	  if [ -s keys/master.key ]; then \
	    cp keys/master.key secrets/master_key && rm -f keys/master.key; \
	    echo "Clé maître déplacée : keys/master.key → secrets/master_key"; \
	  else \
	    python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())" > secrets/master_key; \
	    echo "Clé maître générée : secrets/master_key (à copier hors de la machine)"; \
	  fi; \
	  chmod 644 secrets/master_key; \
	fi

## Arrête et supprime les conteneurs. Les données (comptes, analyses, scénarios, documents,
## clés, sauvegardes) restent sur le disque et sont retrouvées au prochain `make up`.
down:
	$(COMPOSE) down

## Redémarre les conteneurs sans les reconstruire (après une modification du .env).
restart:
	$(COMPOSE) restart

## État des conteneurs (démarré, sain, ports exposés).
status:
	$(COMPOSE) ps

## Reconstruit les images Docker sans démarrer (après une mise à jour du code).
build:
	$(COMPOSE) build

## Suit les journaux de tous les services en direct (Ctrl+C pour quitter).
## Pour un seul service : docker compose logs -f backend
logs:
	$(COMPOSE) logs -f --tail=200

## Suit les journaux des traitements d'arrière-plan : workers Celery (analyses satellitaires,
## synchronisations, notifications) et planificateur.
workers:
	$(COMPOSE) logs -f --tail=100 worker worker-analysis beat

## Console SQL PostgreSQL (lecture / diagnostic). Ex : SELECT COUNT(*) FROM equipments;
psql:
	$(COMPOSE) exec postgres psql -U kap -d kap

## Ouvre la page du serveur de notifications PoC (imitation Slack / Mattermost) : veille,
## analyses, données, décisions, sécurité.
notifs:
	@echo "$(CONSOLE_URL)/notifs/"
	@(xdg-open $(CONSOLE_URL)/notifs/ >/dev/null 2>&1 || open $(CONSOLE_URL)/notifs/ >/dev/null 2>&1) || true

## Reconstruit et redéploie la base de connaissances (service docs, MkDocs Material) après
## une modification des pages docs/content/*.md, puis affiche son adresse.
## Toutes les pages sont vérifiées à la construction (liens et ancres cassés = échec).
docs:
	$(COMPOSE) up -d --build docs
	@echo "$(CONSOLE_URL)/docs/"
	@(xdg-open $(CONSOLE_URL)/docs/ >/dev/null 2>&1 || open $(CONSOLE_URL)/docs/ >/dev/null 2>&1) || true

## Régénère la page « Paramètres opérationnels » de la documentation à partir du code
## (backend/app/services/runtime.py), après l'ajout ou la modification d'un paramètre.
docs-params:
	$(COMPOSE) run --rm --no-deps -v "$(CURDIR)/docs:/docs" -e BACKEND_DIR=/app --entrypoint python backend /docs/tools/gen_parametres.py

##@ Données et analyses

## Synchronise les données ouvertes : communes (geo.api.gouv.fr), statistiques INSEE (Melodi),
## écoles et effectifs (Éducation nationale), équipements (OpenStreetMap). ~1 min.
sync:
	$(RUN_CLI) sync

## Prépare une commune : série du bâti 1985 → aujourd'hui (WSF Evolution, WSF 2019, Sentinel-2),
## bâtiments par carreau, routes, aires protégées, veille. Quelques minutes.
## Ex : make analyse COMMUNE=97311   (Saint-Laurent-du-Maroni)
analyse:
	@test -n "$(COMMUNE)" || (echo "Usage : make analyse COMMUNE=<code INSEE>  (ex. 97311)"; exit 1)
	$(RUN_CLI) analyse $(COMMUNE)

## Réécrit l'instantané hors ligne embarqué (backend/app/reference/snapshot_973.json.gz) à partir
## des données et analyses de cette instance : démonstration sans réseau (salon, terrain).
snapshot:
	$(COMPOSE) run --rm -v "$(CURDIR)/backend/app/reference:/app/app/reference" backend python main.py export-snapshot

##@ Comptes et accès

## Crée un compte ADMINISTRATEUR, sans validation préalable (l'accès à la machine fait
## foi). Mot de passe temporaire affiché une seule fois, à changer à la 1re connexion.
## Création tracée dans l'audit (cli:host) et notifiée (#securite).
## Ex : make admin   ·   make admin NAME=alice
admin:
	@name="$(NAME)"; \
	if [ -z "$$name" ]; then printf "Identifiant du nouvel administrateur : "; read name; fi; \
	if [ -z "$$name" ]; then echo "Annulé : identifiant vide."; exit 1; fi; \
	$(RUN_CLI) create-admin "$$name"

## Affiche le mot de passe temporaire du TOUT PREMIER administrateur (« admin »),
## généré au premier démarrage et visible une seule fois dans les journaux du backend.
admin-password:
	@$(COMPOSE) logs backend 2>/dev/null | grep -A3 "administrator account created" || echo "Aucun mot de passe initial dans les journaux (compte déjà créé ou BOOTSTRAP_ADMIN_PASSWORD défini). Utilisez : make admin"

## Crée un compte d'un rôle donné : viewer (consultation : élus, partenaires),
## analyst (chargé d'études), supervisor (responsable : valide et signe) ou admin. Authentification d'un administrateur exigée.
## Ex : make user NAME=alice ROLE=analyst
user:
	@test -n "$(NAME)" -a -n "$(ROLE)" || (echo "Usage : make user NAME=<identifiant> ROLE=viewer|analyst|supervisor|admin"; exit 1)
	$(RUN_CLI) create-user $(NAME) $(ROLE)

## Liste les comptes : rôle, état (actif, désactivé, mot de passe temporaire) et dernière
## connexion. Aucun secret affiché. Authentification d'un administrateur exigée.
users:
	@$(RUN_CLI) list-users

## Donne un nouveau mot de passe temporaire à un compte, ferme ses sessions et lève un
## éventuel verrouillage. Authentification d'un administrateur exigée ; en secours
## (plus aucun admin ne peut se connecter) : RECOVERY=1 → clé maître demandée.
## Ex : make reset-password NAME=alice   ·   make reset-password NAME=admin RECOVERY=1
reset-password:
	@test -n "$(NAME)" || (echo "Usage : make reset-password NAME=<identifiant> [RECOVERY=1]"; exit 1)
	$(RUN_CLI) reset-password $(NAME) $(RECOVERY_FLAG)

##@ Sauvegarde, remise à neuf, restauration

## Crée une archive de la plateforme (comptes, statistiques, analyses, scénarios, documents
## signés, audit, PKI et secrets chiffrés) dans backups/ (droits 600). La clé maître (secrets/master_key) n'y est PAS :
## conservez-la à part, hors de la machine — sans elle l'archive ne peut pas être relue.
## Authentification d'un administrateur exigée.
backup:
	@mkdir -p backups
	$(RUN_CLI) backup

## Liste les sauvegardes disponibles dans backups/ (taille, date).
backups-list:
	@ls -lh backups/ 2>/dev/null || echo "Aucune sauvegarde."

## Remet la plateforme à neuf. SCOPE=full (défaut) : tout est effacé, clés comprises,
## comme une installation neuve. SCOPE=data : efface comptes, analyses, scénarios, documents,
## audit et paramètres mais garde la PKI et le webhook. La clé maître (secrets/master_key)
## n'est jamais effacée.
## Sécurités : admin authentifié (ou RECOVERY=1), récapitulatif, phrase
## « REINITIALISER KAP » à taper, sauvegarde automatique avant effacement.
## Ex : make reset   ·   make reset SCOPE=data
reset:
	@mkdir -p backups
	@echo "Arrêt de la plateforme pour la réinitialisation…"
	@$(COMPOSE) stop $(APP_SERVICES) >/dev/null 2>&1 || true
	@status=0; $(RUN_CLI) factory-reset --scope $(or $(SCOPE),full) $(RECOVERY_FLAG) || status=$$?; \
	echo "Redémarrage de la plateforme…"; $(COMPOSE) up -d >/dev/null; \
	$(call cli_exit,$$status)

## Remplace tout le contenu de la plateforme par une sauvegarde (l'état courant est
## lui-même sauvegardé avant). Archive contrôlée avant extraction. Admin authentifié
## (ou RECOVERY=1) et phrase de confirmation exigés.
## Ex : make restore FILE=backups/kap-backup-20261024T180000Z.tar.gz
restore:
	@test -n "$(FILE)" || (echo "Usage : make restore FILE=backups/<sauvegarde>.tar.gz  (voir make backups-list)"; exit 1)
	@$(COMPOSE) stop $(APP_SERVICES) >/dev/null 2>&1 || true
	@status=0; $(RUN_CLI) restore "/backups/$(notdir $(FILE))" $(RECOVERY_FLAG) || status=$$?; \
	$(COMPOSE) up -d >/dev/null; \
	$(call cli_exit,$$status)

##@ Sécurité

## Vérifie l'intégrité du journal d'audit : recalcule la chaîne SHA-256 et signale la
## première entrée altérée, supprimée ou déplacée (code retour ≠ 0 si la chaîne est rompue).
verify-audit:
	$(RUN_CLI) verify-audit

## Génère une nouvelle clé maître (Fernet) à placer dans MASTER_KEY, idéalement via un
## gestionnaire de secrets. Ne remplace PAS la clé en place : sans migration, les secrets
## déjà chiffrés avec l'ancienne clé deviendraient illisibles.
master-key:
	@$(RUN_CLI) generate-master-key

##@ Développement

## Crée (ou recrée) un environnement Python local léger dans .venv à partir de
## backend/requirements-dev.txt (dépendances + outils de test, ~300 Mo). Nécessaire seulement pour `make dev` hors Docker ;
## `make test` fonctionne aussi sans, dans le conteneur.
venv:
	python3 -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r backend/requirements-dev.txt
	@echo "Environnement prêt : $(VENV)"

## Lance le backend (rechargement à chaud, :8000) et la console Vite (:5173) en local,
## hors Docker. Prérequis : make venv, et Node.js pour la console.
dev:
	$(MAKE) -j2 dev-backend dev-frontend

## Backend seul en local (uvicorn --reload sur 127.0.0.1:8000, docs API sur /docs).
dev-backend:
	@test -n "$(HAS_VENV)" || (echo "Environnement local absent : lancez d'abord make venv"; exit 1)
	cd backend && ENVIRONMENT=development $(if $(wildcard secrets/master_key),MASTER_KEY_FILE=$(CURDIR)/secrets/master_key) \
	  $(VENV_PYTHON) -m uvicorn server:app --reload --host 127.0.0.1 --port 8000

## Console seule en local (npm install puis Vite sur http://localhost:5173).
dev-frontend:
	cd frontend && npm install && npm run dev

## Lance la suite de tests du backend (sécurité, grille, analyses, décision, rapports…) :
## dans .venv s'il existe, sinon dans le conteneur backend (aucune installation locale).
test:
ifneq ($(HAS_VENV),)
	cd backend && $(VENV_PYTHON) -m pytest -q
else
	$(COMPOSE) --profile test run --rm --no-deps --build backend-test python -m pytest -q -p no:cacheprovider
endif

## Lance la même suite contre PostgreSQL (base de test dédiée kap_test, créée au besoin,
## jamais la base de production). Nécessite la plateforme démarrée (make up).
test-pg:
	@$(COMPOSE) exec -T postgres sh -c 'psql -U kap -d kap -tc "SELECT 1 FROM pg_database WHERE datname = '"'"'kap_test'"'"'" | grep -q 1 || createdb -U kap kap_test'
	$(COMPOSE) --profile test run --rm --build backend-test sh -c 'KAP_TEST_DATABASE_URL="postgresql://kap:$$(cat /run/secrets/postgres_password)@postgres:5432/kap_test" python -m pytest -q -p no:cacheprovider'

## Vérifie que le socle commun (front, sécurité, tests partagés : voir frontend/SHARED.md) est
## identique dans le projet voisin. Ex : make shared-check OTHER=../autre-projet
OTHER ?=
SHARED_FILES := frontend/SHARED.md frontend/tailwind.config.js frontend/postcss.config.js frontend/vite.config.js frontend/src/main.jsx frontend/src/index.css frontend/src/components/ui.jsx frontend/src/components/AppShell.jsx frontend/src/components/ErrorBoundary.jsx frontend/src/components/DocLink.jsx frontend/src/components/Printable.jsx frontend/src/lib/format.js frontend/src/lib/dates.js frontend/src/services/client.js frontend/src/views/LoginView.jsx frontend/src/views/AuditView.jsx frontend/src/views/UsersTab.jsx frontend/src/views/CustomSourcesTab.jsx frontend/40-tls.sh frontend/Dockerfile backend/tests/test_shared_core.py backend/app/core/audit.py backend/app/core/ratelimit.py backend/app/core/vault.py backend/app/core/geo.py backend/app/api/endpoints/auth.py backend/app/api/endpoints/audit_log.py backend/app/api/endpoints/custom_sources.py docs/nginx.conf $(wildcard frontend/public/fonts/*.woff2)
shared-check:
	@test -n "$(OTHER)" -a -d "$(OTHER)" || (echo "Projet voisin introuvable : $(OTHER) (OTHER=…)"; exit 2)
	@status=0; for f in $(SHARED_FILES); do \
		if cmp -s "$$f" "$(OTHER)/$$f"; then :; else echo "  ✘ diffère : $$f"; status=1; fi; \
	 done; \
	 if [ $$status -eq 0 ]; then echo "  ✔ socle commun identique à $(OTHER)"; fi; exit $$status

