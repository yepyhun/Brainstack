from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

import pytest

from brainstack.db import BrainstackStore
from brainstack.db_migrations import (
    COMPATIBILITY_MIGRATIONS,
    KNOWN_MIGRATION_NAMES,
    mark_migration_applied,
    run_compatibility_migrations,
    unknown_applied_migration_names,
)
from brainstack.db_schema import initialize_schema


class _FakeMigrationStore:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        initialize_schema(self.conn)
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Callable[[], None]:
        for spec in COMPATIBILITY_MIGRATIONS:
            if spec.method_name != name:
                continue

            def migration(spec_name: str = spec.name) -> None:
                self.calls.append(spec_name)
                mark_migration_applied(self.conn, spec_name)

            return migration
        raise AttributeError(name)


def _applied_names(store: BrainstackStore) -> tuple[str, ...]:
    rows = store.conn.execute("SELECT name FROM applied_migrations ORDER BY name ASC").fetchall()
    return tuple(str(row["name"]) for row in rows)


def test_migration_runner_applies_missing_migrations_once_in_declared_order() -> None:
    store = _FakeMigrationStore()

    run_compatibility_migrations(store)
    first_calls = tuple(store.calls)

    run_compatibility_migrations(store)

    assert first_calls == tuple(spec.name for spec in COMPATIBILITY_MIGRATIONS)
    assert tuple(store.calls) == first_calls
    assert unknown_applied_migration_names(store.conn) == ()


def test_migration_runner_fails_closed_when_declared_method_is_missing() -> None:
    class BrokenStore:
        def __init__(self) -> None:
            self.conn = sqlite3.connect(":memory:")
            self.conn.row_factory = sqlite3.Row
            initialize_schema(self.conn)

    with pytest.raises(RuntimeError, match="migration method missing"):
        run_compatibility_migrations(BrokenStore())


def test_store_migration_ledger_is_stable_across_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "brainstack.sqlite"
    store = BrainstackStore(str(db_path))
    try:
        store.open()
        first = _applied_names(store)
    finally:
        store.close()

    store = BrainstackStore(str(db_path))
    try:
        store.open()
        second = _applied_names(store)
        assert first == second
        assert set(KNOWN_MIGRATION_NAMES).issubset(set(second))
        assert unknown_applied_migration_names(store.conn) == ()
    finally:
        store.close()
