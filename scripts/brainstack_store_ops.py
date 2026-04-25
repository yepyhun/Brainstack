#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._brainstack_host_shim import install_host_shim_if_needed  # noqa: E402

install_host_shim_if_needed()

from brainstack.db_ops import backup_sqlite_store, migration_dry_run_report, restore_sqlite_store  # noqa: E402


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_backup(args: argparse.Namespace) -> int:
    receipt = backup_sqlite_store(source_path=args.db, backup_path=args.out)
    _print_json(receipt)
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    receipt = restore_sqlite_store(backup_path=args.backup, target_path=args.db)
    _print_json(receipt)
    return 0


def _cmd_migration_report(args: argparse.Namespace) -> int:
    report = migration_dry_run_report(args.db)
    _print_json(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explicit Brainstack SQLite store backup, restore, and migration reporting.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Copy a Brainstack SQLite DB to an explicit backup path.")
    backup.add_argument("--db", required=True, type=Path, help="Source Brainstack SQLite DB path.")
    backup.add_argument("--out", required=True, type=Path, help="Backup output path.")
    backup.set_defaults(func=_cmd_backup)

    restore = subparsers.add_parser("restore", help="Restore a Brainstack SQLite DB from an explicit backup path.")
    restore.add_argument("--backup", required=True, type=Path, help="Source backup path.")
    restore.add_argument("--db", required=True, type=Path, help="Target Brainstack SQLite DB path.")
    restore.set_defaults(func=_cmd_restore)

    report = subparsers.add_parser("migration-report", help="Read-only Brainstack migration/substrate report.")
    report.add_argument("--db", required=True, type=Path, help="Brainstack SQLite DB path.")
    report.add_argument("--json", action="store_true", help="Retained for explicit machine-readable output; JSON is always used.")
    report.set_defaults(func=_cmd_migration_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        _print_json(
            {
                "schema": "brainstack.store_ops_error.v1",
                "status": "error",
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
