"""Persistence: embedded SQLite or PostgreSQL, same application code.

- **SQLite** (``DATABASE_URL`` empty): one short-lived connection per unit of work,
  WAL journaling, foreign keys on. Development, tests, single-host deployments.
- **PostgreSQL** (``DATABASE_URL=postgresql://…``): connection pool per process,
  UTC session time zone, advisory locks for read-modify-write sequences.

Application SQL uses the portable subset (``?`` placeholders, ``ON CONFLICT``,
``RETURNING``); this module adapts placeholders and ``LIKE`` for PostgreSQL and
returns rows that behave like ``sqlite3.Row`` (index and column-name access).
"""

from __future__ import annotations

import atexit
import datetime
import logging
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialised: set = set()

# Schema written once for both engines: {ID} / {REAL} / {USERNAME} differ by dialect.
_SCHEMA_V1 = """
CREATE TABLE users (
    id {ID},
    username TEXT NOT NULL{USERNAME},
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('viewer','analyst','supervisor','admin')),
    password_hash TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    disabled INTEGER NOT NULL DEFAULT 0,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    password_changed_at TEXT NOT NULL
);
{USERNAME_INDEX}
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id {FK} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ip TEXT,
    user_agent TEXT
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE TABLE audit_log (
    id {ID},
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'success',
    ip TEXT,
    details TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX idx_audit_target ON audit_log(target);
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
-- Territory: the 22 communes (boundaries, legal population) and their statistics.
CREATE TABLE communes (
    code TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    epci TEXT NOT NULL DEFAULT '',
    population INTEGER,
    surface_ha {REAL},
    centre_lat {REAL},
    centre_lon {REAL},
    bbox TEXT NOT NULL DEFAULT '[]',
    contour TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE indicators (
    geo TEXT NOT NULL,
    indicator TEXT NOT NULL,
    year INTEGER NOT NULL,
    value {REAL},
    source TEXT NOT NULL DEFAULT '',
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (geo, indicator, year)
);
CREATE INDEX idx_indicators_indicator ON indicators(indicator, year);
-- Elected officials' own population figure (e.g. town hall estimate), shown next to the
-- INSEE legal population and usable as an explicit planning hypothesis.
CREATE TABLE population_hypotheses (
    commune_code TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    value INTEGER NOT NULL,
    low INTEGER,
    high INTEGER,
    source TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
-- Public facilities and everyday services (schools, health, water, food, transport…),
-- from open data or entered by the services (existing, provisional or planned).
CREATE TABLE equipments (
    id {ID},
    uid TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    subtype TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    commune_code TEXT,
    lat {REAL} NOT NULL,
    lon {REAL} NOT NULL,
    capacity {REAL},
    capacity_unit TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'existant' CHECK (status IN ('existant','provisoire','projet')),
    source TEXT NOT NULL,
    attributes TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
CREATE INDEX idx_equipments_commune ON equipments(commune_code, category);
-- Analysis grid layers (200 m cells, sparse): built-up series, population estimate…
CREATE TABLE grid_layers (
    commune_code TEXT NOT NULL,
    layer TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    payload TEXT NOT NULL,
    PRIMARY KEY (commune_code, layer)
);
CREATE TABLE analysis_jobs (
    id {ID},
    kind TEXT NOT NULL,
    commune_code TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    steps TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX idx_jobs_commune ON analysis_jobs(commune_code, created_at);
-- Siting scenarios: candidate locations of a new facility and their measured effect.
CREATE TABLE scenarios (
    id {ID},
    commune_code TEXT NOT NULL,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sites TEXT NOT NULL DEFAULT '[]',
    params TEXT NOT NULL DEFAULT '{}',
    evaluation TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'brouillon' CHECK (status IN ('brouillon','valide','archive')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
CREATE INDEX idx_scenarios_commune ON scenarios(commune_code);
-- Register of signed decision documents (commune brief, siting file, census list…).
CREATE TABLE reports (
    id {ID},
    ref TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    commune_code TEXT,
    scenario_id {FK} REFERENCES scenarios(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    classification TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    content TEXT NOT NULL,
    sections TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    signature TEXT NOT NULL DEFAULT '',
    cert_fingerprint TEXT NOT NULL DEFAULT '',
    certificate TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_reports_created ON reports(created_at);
"""

_SQLITE = {"ID": "INTEGER PRIMARY KEY", "FK": "INTEGER", "REAL": "REAL", "USERNAME": " UNIQUE COLLATE NOCASE",
           "USERNAME_INDEX": ""}
_PG = {"ID": "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", "FK": "BIGINT", "REAL": "DOUBLE PRECISION",
       "USERNAME": "", "USERNAME_INDEX": "CREATE UNIQUE INDEX idx_users_username ON users (lower(username));"}


def _render(template: str, dialect: Dict[str, str]) -> str:
    return re.sub(r"\{([A-Z_]+)\}", lambda m: dialect[m.group(1)], template)


# v2 — local corrections of open-data facilities (position, capacity, status, note), kept
# across synchronisations; validation of the satellite layer by visual control.
_SCHEMA_V2 = """
CREATE TABLE equipment_overrides (
    uid TEXT PRIMARY KEY,
    lat {REAL},
    lon {REAL},
    capacity {REAL},
    capacity_unit TEXT,
    status TEXT,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
CREATE TABLE validations (
    id {ID},
    commune_code TEXT NOT NULL,
    cell TEXT NOT NULL,
    year INTEGER NOT NULL,
    predicted REAL NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('bati','non_bati','incertain')),
    imagery TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE (commune_code, cell, year, created_by)
);
CREATE INDEX idx_validations_commune ON validations(commune_code, year);
"""

# v3 — indexes of the frequent lookups: expired-session purge (every login), audit filters by
# action and actor, pending jobs (every analysis request), facilities of a source (every sync).
_SCHEMA_V3 = """
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_equipments_source ON equipments(source);
"""

MIGRATIONS: List[str] = [_render(s, _SQLITE) for s in (_SCHEMA_V1, _SCHEMA_V2, _SCHEMA_V3)]
PG_MIGRATIONS: List[str] = [_render(s, _PG) for s in (_SCHEMA_V1, _SCHEMA_V2, _SCHEMA_V3)]

# Tables in foreign-key order (dump / restore / wipe).
TABLES = (
    "users", "sessions", "audit_log", "app_settings", "communes", "indicators", "population_hypotheses",
    "equipments", "grid_layers", "analysis_jobs", "scenarios", "reports", "equipment_overrides", "validations",
)
IDENTITY_TABLES = ("users", "audit_log", "equipments", "analysis_jobs", "scenarios", "reports", "validations")


def is_postgres(settings: Optional[Settings] = None) -> bool:
    return (settings or get_settings()).database_url.startswith(("postgres://", "postgresql://"))


def database_dsn(cfg: Settings) -> str:
    """DATABASE_URL with the password from DATABASE_PASSWORD_FILE (docker secret) when given."""
    url = cfg.database_url
    path = cfg.database_password_file
    if path and os.path.isfile(path):
        from urllib.parse import quote, urlsplit, urlunsplit

        password = Path(path).read_text(encoding="utf-8").strip()
        parts = urlsplit(url)
        user = parts.username or ""
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        url = urlunsplit((parts.scheme, f"{quote(user, safe='')}:{quote(password, safe='')}@{host}{port}", parts.path, parts.query, parts.fragment))
    return url


# --------------------------------------------------------------------------- rows & SQL adaptation


class Row(tuple):
    """Tuple with column-name access, ``keys()`` and ``dict(row)`` support (like sqlite3.Row)."""

    def __new__(cls, names: Sequence[str], values: Sequence[Any]) -> "Row":
        obj = super().__new__(cls, values)
        obj._names = tuple(names)
        return obj

    def __getitem__(self, key: Any) -> Any:  # type: ignore[override]
        if isinstance(key, str):
            return tuple.__getitem__(self, self._names.index(key))
        return tuple.__getitem__(self, key)

    def keys(self) -> List[str]:
        return list(self._names)


def _plain(value: Any) -> Any:
    """TIMESTAMPTZ values come back as the ISO strings the application stores elsewhere."""
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.timezone.utc).isoformat()
    return value


def _row_factory(cursor: Any) -> Any:
    names = [column.name for column in (cursor.description or [])]

    def make(values: Sequence[Any]) -> Row:
        return Row(names, [_plain(v) for v in values])

    return make


_PLACEHOLDER = re.compile(r"'[^']*'|\?")
_LIKE = re.compile(r"\bLIKE\b")


@lru_cache(maxsize=512)
def to_postgres(sql: str) -> str:
    """``?`` placeholders -> ``%s`` (outside string literals), ``%`` escaped, LIKE -> ILIKE."""
    sql = sql.replace("%", "%%")
    sql = _PLACEHOLDER.sub(lambda m: "%s" if m.group(0) == "?" else m.group(0), sql)
    return _LIKE.sub("ILIKE", sql)


class _Result:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self) -> Optional[Row]:
        return self._cursor.fetchone() if self._cursor.description else None

    def fetchall(self) -> List[Row]:
        return self._cursor.fetchall() if self._cursor.description else []

    def __iter__(self) -> Iterator[Row]:
        return iter(self.fetchall())

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


class PgConnection:
    """sqlite3-like facade over a psycopg connection (execute / executemany / rows)."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _Result:
        cursor = self._conn.cursor(row_factory=_row_factory)
        if isinstance(params, dict):
            cursor.execute(re.sub(r":(\w+)", r"%(\1)s", sql.replace("%", "%%")), params)
        else:
            cursor.execute(to_postgres(sql), tuple(params) if params else None)
        return _Result(cursor)

    def executemany(self, sql: str, seq: Sequence[Sequence[Any]]) -> None:
        with self._conn.cursor() as cursor:
            cursor.executemany(to_postgres(sql), [tuple(p) for p in seq])

    @property
    def raw(self) -> Any:
        return self._conn


# --------------------------------------------------------------------------- PostgreSQL pool

_pools: Dict[Any, Any] = {}
_pools_lock = threading.Lock()
_pg_initialised: set = set()


def _configure(conn: Any) -> None:
    conn.execute("SET TIME ZONE 'UTC'")
    conn.commit()


def _pool(cfg: Settings) -> Any:
    from psycopg_pool import ConnectionPool

    key = (os.getpid(), cfg.database_url)  # one pool per process (Celery prefork safe)
    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            pool = ConnectionPool(
                database_dsn(cfg), min_size=1, max_size=max(2, cfg.database_pool_size),
                configure=_configure, open=True, timeout=30, name=f"kap-{os.getpid()}",
            )
            _pools[key] = pool
    return pool


def close_pools() -> None:
    with _pools_lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()
    _pg_initialised.clear()


atexit.register(close_pools)


def _init_postgres(cfg: Settings) -> None:
    pool = _pool(cfg)
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_lock(7262001)")  # one process migrates at a time
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
            for index, script in enumerate(PG_MIGRATIONS[current:], start=current + 1):
                with conn.transaction():
                    conn.execute(script)
                    conn.execute("INSERT INTO schema_version (version) VALUES (%s)", (index,))
                logger.info("PostgreSQL schema migrated to v%s", index)
            conn.commit()
        finally:
            conn.execute("SELECT pg_advisory_unlock(7262001)")
            conn.commit()


# --------------------------------------------------------------------------- SQLite


def _db_path(cfg: Settings) -> Path:
    return Path(cfg.data_dir) / "kap.db"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    # WAL + NORMAL: durable at each checkpoint, no fsync per commit (safe against application
    # crashes; a power loss can only lose the last transactions, never corrupt the file).
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(settings: Optional[Settings] = None) -> Any:
    """Create / migrate the schema of the configured database."""
    cfg = settings or get_settings()
    if is_postgres(cfg):
        with _init_lock:
            _init_postgres(cfg)
            _pg_initialised.add(cfg.database_url)
        return cfg.database_url
    path = _db_path(cfg)
    with _init_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch(mode=0o600)
        conn = _connect(path)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for index, script in enumerate(MIGRATIONS[version:], start=version + 1):
                conn.executescript(f"BEGIN; {script} PRAGMA user_version = {index}; COMMIT;")
        finally:
            conn.close()
        _initialised.add(str(path))
    return path


@contextmanager
def _pg_transaction(cfg: Settings, read_only: bool) -> Iterator[PgConnection]:
    if cfg.database_url not in _pg_initialised:
        init_db(cfg)
    with _pool(cfg).connection() as conn:
        with conn.transaction():
            if read_only:
                conn.execute("SET TRANSACTION READ ONLY")
            yield PgConnection(conn)


@contextmanager
def db(settings: Optional[Settings] = None) -> Iterator[Any]:
    """Write transaction: commits on success, rolls back on error."""
    cfg = settings or get_settings()
    if is_postgres(cfg):
        with _pg_transaction(cfg, read_only=False) as conn:
            yield conn
        return
    path = _db_path(cfg)
    if str(path) not in _initialised:
        init_db(cfg)
    conn = _connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def read_db(settings: Optional[Settings] = None) -> Iterator[Any]:
    """Read-only snapshot: never takes a write lock, so reads never queue behind writers.

    Any accidental write fails loudly (``query_only`` / ``READ ONLY`` transaction).
    """
    cfg = settings or get_settings()
    if is_postgres(cfg):
        with _pg_transaction(cfg, read_only=True) as conn:
            yield conn
        return
    path = _db_path(cfg)
    if str(path) not in _initialised:
        init_db(cfg)
    conn = _connect(path)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def lock(conn: Any, name: str) -> None:
    """Serialise a read-modify-write sequence across processes for the rest of the transaction.

    SQLite write transactions (BEGIN IMMEDIATE) are already exclusive; PostgreSQL takes a
    transaction-scoped advisory lock (e.g. the audit hash chain must never fork).
    """
    if isinstance(conn, PgConnection):
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (name,))


def row(r: Any) -> Optional[Dict[str, Any]]:
    return dict(r) if r is not None else None


def rows(rs: Sequence[Any]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rs]
