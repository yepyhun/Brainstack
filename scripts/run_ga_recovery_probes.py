#!/usr/bin/env python3
"""Write Phase 188 install/upgrade/recovery artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ga_recovery import (  # noqa: E402
    backup_restore_roundtrip,
    clean_install_probe,
    migration_report,
    recovery_commands,
    rollback_proof,
    sha256_tree,
    write_json,
)
from scripts.phase185_rc_gate import source_wizard_docker_parity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-root", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    hermes_root = Path(args.hermes_root).resolve()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest_path = hermes_root / ".brainstack-install-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    install = clean_install_probe(manifest)
    write_json(out / "188-INSTALL-UPGRADE-MATRIX.json", {"schema": "brainstack.phase188.install_upgrade_matrix.v1", "clean_install": install})

    migration = migration_report(before_version=1, after_version=2, backup_present=True, dry_run=True)
    write_json(out / "188-MIGRATION-REPORT.json", migration)

    fixture = out / "backup-fixture"
    source = fixture / "source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "brainstack.db").write_text("memory", encoding="utf-8")
    (source / "profile.json").write_text('{"name":"Alex"}', encoding="utf-8")
    backup = fixture / "backup"
    restored = fixture / "restored"
    backup_proof = backup_restore_roundtrip(source, backup, restored)
    write_json(out / "188-BACKUP-RESTORE-PROOF.json", backup_proof)

    previous = {"brainstack/product_contracts.py": "old", "brainstack/__init__.py": "init"}
    current = sha256_tree(hermes_root / "plugins" / "memory")
    rollback = rollback_proof(current, previous)
    write_json(out / "188-ROLLBACK-PROOF.json", rollback)

    parity = source_wizard_docker_parity(ROOT, hermes_root)
    write_json(out / "188-SOURCE-WIZARD-DOCKER-PARITY.json", parity)

    (out / "188-RECOVERY-COMMANDS.md").write_text(recovery_commands(), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
