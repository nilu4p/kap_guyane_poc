"""Database engines: SQL adaptation, portable dumps, PostgreSQL specifics."""

from __future__ import annotations

import datetime
import threading
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings, get_settings
from app.core import audit, dbtransfer
from app.db import Row, db, init_db, read_db, to_postgres
from tests.conftest import postgres_only

NOW = datetime.datetime.now(datetime.timezone.utc)


def test_sql_adaptation_for_postgres() -> None:
    assert to_postgres("SELECT * FROM t WHERE a = ? AND b LIKE ?") == "SELECT * FROM t WHERE a = %s AND b ILIKE %s"
    assert to_postgres("SELECT '?' , x FROM t WHERE y = ?") == "SELECT '?' , x FROM t WHERE y = %s"
    assert to_postgres("SELECT 100 % 7") == "SELECT 100 %% 7"
    row = Row(["id", "name"], [1, "a"])
    assert row[0] == 1 and row["name"] == "a" and dict(row) == {"id": 1, "name": "a"}


def test_logical_dump_restores_on_any_engine(tmp_path: Path) -> None:
    from app.territoire import store

    store.ensure_communes()
    store.save_manual_equipment({"category": "eau", "lat": 5.49, "lon": -54.02, "status": "projet", "name": "Borne"}, "t")
    audit.record("test.event", actor="t")
    dbtransfer.write_jsonl(tmp_path / "dump")
    target = Settings(database_url="", data_dir=tmp_path / "other")  # always SQLite
    counts = dbtransfer.load_jsonl(tmp_path / "dump", target)
    assert counts["communes"] == 22 and counts["equipments"] == 1 and counts["audit_log"] >= 1
    assert audit.verify_chain(target)["valid"]


@postgres_only
def test_audit_chain_never_forks_under_concurrency() -> None:
    def burst(n: int) -> None:
        for i in range(10):
            audit.record("test.concurrent", actor=f"t{n}", details={"i": i})

    threads = [threading.Thread(target=burst, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result = audit.verify_chain()
    assert result["valid"] and result["entries"] == 60
