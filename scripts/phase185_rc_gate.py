"""Phase 185 source/wizard/Docker/live RC gate helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping


CRITICAL_PAYLOAD_FILES: tuple[str, ...] = (
    "brainstack/product_contracts.py",
    "brainstack/__init__.py",
)


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_targets(hermes_root: Path) -> dict[str, Path]:
    manifest_path = hermes_root / ".brainstack-install-manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    targets: dict[str, Path] = {}
    for row in manifest.get("files", []):
        if not isinstance(row, dict):
            continue
        source = row.get("source")
        target = row.get("target")
        if isinstance(source, str) and isinstance(target, str):
            targets[source] = Path(target)
    return targets


def _installed_target(hermes_root: Path, rel: str, manifest_targets: Mapping[str, Path]) -> Path:
    if rel in manifest_targets:
        return manifest_targets[rel]
    # Fresh test fixtures may not have an installer manifest. Real Hermes installs
    # place Brainstack under plugins/memory/brainstack.
    plugin_rel = Path("plugins") / "memory" / rel
    if (hermes_root / plugin_rel).exists():
        return hermes_root / plugin_rel
    return hermes_root / rel


def source_wizard_docker_parity(source_root: Path, hermes_root: Path, rels: Iterable[str] = CRITICAL_PAYLOAD_FILES) -> dict[str, Any]:
    rows = []
    manifest_targets = _manifest_targets(hermes_root)
    for rel in rels:
        source = source_root / rel
        target = _installed_target(hermes_root, rel, manifest_targets)
        source_hash = sha256_file(source)
        target_hash = sha256_file(target)
        rows.append(
            {
                "path": rel,
                "target_path": str(target),
                "target_from_manifest": rel in manifest_targets,
                "source_exists": source_hash is not None,
                "target_exists": target_hash is not None,
                "source_hash": source_hash,
                "target_hash": target_hash,
                "hash_match": source_hash is not None and source_hash == target_hash,
            }
        )
    return {
        "schema": "brainstack.phase185.source_wizard_docker_parity.v1",
        "manifest_present": bool(manifest_targets),
        "rows": rows,
        "all_hashes_match": all(row["hash_match"] for row in rows),
    }


def docker_adversarial_proof(path: Path | None, status: str) -> dict[str, Any]:
    if path is None:
        return {
            "schema": "brainstack.phase185.docker_adversarial_proof.v1",
            "status": status,
            "proof_present": False,
            "passed": False,
            "checks": {},
        }
    if not path.exists():
        return {
            "schema": "brainstack.phase185.docker_adversarial_proof.v1",
            "status": status,
            "proof_present": False,
            "passed": False,
            "checks": {},
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    checks = data.get("checks", data)
    required = {
        "path_used_firewall": True,
        "path_used_url_guard": True,
        "url_content_claims_allowed": False,
        "style_removed_decorative_prefix": True,
    }
    passed = status == "run_pass" and all(checks.get(key) == expected for key, expected in required.items())
    passed = passed and "ASSISTANT_CLAIM_NOT_MODEL_FACING" in set(checks.get("dropped_reasons", []))
    passed = passed and checks.get("reference_recall") == "https://example.com/org/resource-x"
    return {
        "schema": "brainstack.phase185.docker_adversarial_proof.v1",
        "status": status,
        "proof_present": True,
        "passed": passed,
        "checks": checks,
    }


def generated_config_not_kawaii(config_text: str) -> dict[str, Any]:
    lowered = config_text.casefold()
    bad = "kawaii" in lowered or "personality: cute" in lowered
    return {
        "schema": "brainstack.phase185.config_personality.v1",
        "not_kawaii": not bad,
        "neutral_required": True,
    }


def clean_runtime_state(root: Path, *, apply: bool = False) -> dict[str, Any]:
    removable = ("sessions", "memories", "logs", "brainstack_state")
    preserved = ("auth.json", "auth.lock", "config.yaml", "skills")
    removed: list[str] = []
    preserved_present: list[str] = []
    for name in preserved:
        if (root / name).exists():
            preserved_present.append(name)
    for name in removable:
        path = root / name
        if path.exists():
            removed.append(name)
            if apply:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
    return {
        "schema": "brainstack.phase185.runtime_clean.v1",
        "apply": apply,
        "removed": removed,
        "preserved_present": preserved_present,
        "auth_config_skills_preserved": all(name in preserved_present for name in ("auth.json", "config.yaml", "skills") if (root / name).exists()),
    }


def release_hygiene_blocks_critical_untracked(status_lines: Iterable[str]) -> dict[str, Any]:
    critical = set(CRITICAL_PAYLOAD_FILES)
    blocked = []
    for line in status_lines:
        text = line.strip()
        if not text.startswith("?? "):
            continue
        path = text[3:]
        if path in critical or path.startswith("brainstack/") or path.startswith("scripts/") or path.startswith("tests/"):
            blocked.append(path)
    return {
        "schema": "brainstack.phase185.release_hygiene_untracked.v1",
        "blocked": blocked,
        "blocks_release": bool(blocked),
    }


def rc_matrix(
    *,
    parity: Mapping[str, Any],
    runtime_clean: Mapping[str, Any],
    docker_adversarial_passed: bool,
    live_gate_status: str,
    open_failure_bundles: int,
) -> dict[str, Any]:
    probes = [
        {
            "id": "source_wizard_docker_parity",
            "severity": "P0",
            "status": "pass" if parity.get("all_hashes_match") else "fail",
        },
        {
            "id": "runtime_clean_safe",
            "severity": "P1",
            "status": "pass" if runtime_clean.get("auth_config_skills_preserved") else "fail",
        },
        {
            "id": "docker_adversarial_rc",
            "severity": "P1",
            "status": "pass" if docker_adversarial_passed else "blocked",
        },
        {
            "id": "live_gate",
            "severity": "P1",
            "status": "pass" if live_gate_status == "run_pass" else "blocked",
        },
        {
            "id": "open_failure_bundles",
            "severity": "P0",
            "status": "pass" if open_failure_bundles == 0 else "fail",
        },
    ]
    blocking = [probe for probe in probes if probe["severity"] in {"P0", "P1"} and probe["status"] != "pass"]
    return {
        "schema": "brainstack.phase185.live_rc_matrix.v1",
        "ready": not blocking,
        "probes": probes,
        "blocking": blocking,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
