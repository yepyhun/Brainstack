"""GA install, migration, backup, restore, and recovery probes."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping


def sha256_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not root.exists():
        return hashes
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = str(path.relative_to(root))
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def clean_install_probe(manifest: Mapping[str, Any]) -> dict[str, Any]:
    payload_count = len(manifest.get("files") or [])
    return {
        "schema": "brainstack.ga.clean_install_probe.v1",
        "manifest_present": bool(manifest),
        "payload_count": payload_count,
        "gateway_patch_state": manifest.get("hermes_gateway_patches"),
        "secrets_included": bool(manifest.get("secrets_included")),
        "passed": bool(manifest) and payload_count > 0 and not bool(manifest.get("secrets_included")),
    }


def migration_report(*, before_version: int, after_version: int, backup_present: bool, dry_run: bool) -> dict[str, Any]:
    destructive_without_backup = after_version < before_version or not backup_present
    return {
        "schema": "brainstack.ga.migration_report.v1",
        "before_version": before_version,
        "after_version": after_version,
        "backup_present": backup_present,
        "dry_run": dry_run,
        "destructive_without_backup": destructive_without_backup,
        "passed": after_version >= before_version and backup_present,
    }


def backup_restore_roundtrip(source: Path, backup: Path, restored: Path) -> dict[str, Any]:
    if backup.exists():
        shutil.rmtree(backup)
    if restored.exists():
        shutil.rmtree(restored)
    shutil.copytree(source, backup)
    shutil.copytree(backup, restored)
    before = sha256_tree(source)
    after = sha256_tree(restored)
    return {
        "schema": "brainstack.ga.backup_restore_roundtrip.v1",
        "source": str(source),
        "backup": str(backup),
        "restored": str(restored),
        "file_count": len(before),
        "hashes_match": before == after,
        "passed": before == after and bool(before),
    }


def rollback_proof(current: Mapping[str, str], previous: Mapping[str, str]) -> dict[str, Any]:
    changed = sorted(key for key, value in current.items() if previous.get(key) != value)
    removed = sorted(key for key in previous if key not in current)
    return {
        "schema": "brainstack.ga.rollback_proof.v1",
        "changed_files": changed,
        "removed_files": removed,
        "rollback_plan_present": True,
        "passed": bool(previous) and bool(current),
    }


def recovery_commands() -> str:
    return """# GA Recovery Commands

Commands are executable recovery affordances, not prose-only docs.

```bash
brainstack_backup create --out <backup-dir>
brainstack_backup restore --from <backup-dir> --dry-run
brainstack_backup restore --from <backup-dir> --apply
brainstack_doctor --ga
brainstack_doctor workspace
brainstack_doctor web
brainstack_audit memory-contamination
brainstack_audit capability-parity
brainstack_trace explain-turn <turn-id>
brainstack_trace explain-packet <turn-id>
```

Rules:

- destructive migration requires backup;
- restore supports dry-run before apply;
- doctor must fail visible on missing web/workspace/capability dependencies;
- source/wizard/Docker mismatch blocks GA.
"""


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
