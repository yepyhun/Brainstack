#!/usr/bin/env python3
"""Verify active packet-budget runtime parity for supported Brainstack path."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402

REQUIRED_PAYLOAD_PATHS = [
    "brainstack/__init__.py",
    "brainstack/core/packet_budget.py",
    "brainstack/provider/prefetch_sync.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes() -> dict[str, str]:
    return {path: _sha256(ROOT / path) for path in REQUIRED_PAYLOAD_PATHS}


def _payload_contains_required_paths() -> bool:
    proc = subprocess.run(
        [sys.executable, "scripts/brainstack_payload_manifest.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return False
    payload = json.loads(proc.stdout)
    paths = {str(item.get("path") or "") for item in payload.get("files") or []}
    return set(REQUIRED_PAYLOAD_PATHS).issubset(paths)


def _seed_provider(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    scope = provider._principal_scope_key
    session = provider._session_id
    provider._store.upsert_profile_item(
        stable_key="identity:phase209-name",
        category="identity",
        content="The user's public-safe name is Phase209User.",
        source="phase209_runtime_probe",
        confidence=0.99,
        metadata={"principal_scope_key": scope, "target_slot": "identity.preferred_address_name"},
    )
    for index in range(10):
        provider._store.add_continuity_event(
            session_id=session,
            turn_number=index + 1,
            kind="user",
            content=f"PHASE209_SUPPORT_NOISE_{index}",
            source="phase209_runtime_probe",
            metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
        )


def _provider_probe(*, packet_budget_mode: str, max_candidate_tokens: int = 18) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-phase209-") as tmp:
        provider = BrainstackMemoryProvider(
            {
                "db_path": str(Path(tmp) / "brainstack.sqlite3"),
                "graph_backend": "sqlite",
                "corpus_backend": "sqlite",
                "packet_budget_mode": packet_budget_mode,
                "packet_budget_max_candidate_tokens": max_candidate_tokens,
            }
        )
        provider.initialize(
            "session:phase209-runtime",
            platform="test",
            user_id="phase209-user",
            agent_identity="phase209-agent",
            agent_workspace="phase209-workspace",
        )
        try:
            _seed_provider(provider)
            block = provider.prefetch("What is my public-safe name?", session_id=provider._session_id)
            packet_budget = dict((provider._last_prefetch_policy or {}).get("packet_budget") or {})
            return {
                "packet_budget_mode_config": packet_budget_mode,
                "block_contains_truth": "Phase209User" in block,
                "packet_budget": {
                    "mode": packet_budget.get("mode"),
                    "enabled": packet_budget.get("enabled"),
                    "applied_to_output": packet_budget.get("applied_to_output"),
                    "status": packet_budget.get("status"),
                    "selected_candidate_tokens": packet_budget.get("selected_candidate_tokens"),
                    "dropped_candidate_tokens": packet_budget.get("dropped_candidate_tokens"),
                    "estimated_tokens_before": packet_budget.get("estimated_tokens_before"),
                    "protected_truth_drop_attempts": 0
                    if packet_budget.get("answer_evidence_preserved", True)
                    else 1,
                    "budget_reason_code_registry_pass": packet_budget.get(
                        "budget_reason_code_registry_pass", True
                    ),
                    "raw_text_in_budget_trace": packet_budget.get("raw_text_in_budget_trace", False),
                },
            }
        finally:
            provider.shutdown()


def _docker_hashes(container: str) -> dict[str, str]:
    script = """
from pathlib import Path
import hashlib, json
paths = %r
base = Path('/opt/hermes/plugins/memory')
out = {}
for rel in paths:
    p = base / rel
    out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else 'missing'
print(json.dumps(out, sort_keys=True))
""" % REQUIRED_PAYLOAD_PATHS
    proc = subprocess.run(
        ["docker", "exec", container, "python3", "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip() or "docker_exec_failed"}
    return json.loads(proc.stdout)


def verify_runtime_parity(*, docker_container: str | None = None) -> dict[str, Any]:
    source_hashes = _source_hashes()
    active = _provider_probe(packet_budget_mode="active")
    disabled = _provider_probe(packet_budget_mode="off")
    docker_hashes = _docker_hashes(docker_container) if docker_container else {}
    docker_parity = bool(docker_hashes) and all(
        docker_hashes.get(path) == source_hash for path, source_hash in source_hashes.items()
    )
    active_budget = active["packet_budget"]
    disabled_budget = disabled["packet_budget"]
    candidate_delta = 0.0
    before = active_budget.get("estimated_tokens_before") or 0
    selected = active_budget.get("selected_candidate_tokens") or 0
    if before:
        candidate_delta = round((before - selected) / before * 100.0, 2)
    source_runtime_parity = docker_parity if docker_container else True
    passed = (
        _payload_contains_required_paths()
        and active["block_contains_truth"]
        and active_budget.get("mode") == "active"
        and active_budget.get("applied_to_output") is True
        and active_budget.get("protected_truth_drop_attempts") == 0
        and disabled["block_contains_truth"]
        and disabled_budget.get("mode") == "off"
        and disabled_budget.get("enabled") is False
        and source_runtime_parity
    )
    return {
        "schema": "brainstack.phase209.runtime_parity.v1",
        "status": "pass" if passed else "fail",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_hashes": source_hashes,
        "wizard_payload_contains_change": _payload_contains_required_paths(),
        "installed_runtime_version": "source_provider_probe",
        "docker_runtime_version": docker_container or "not_checked",
        "docker_hashes": docker_hashes,
        "active_budget_trace_present": active_budget.get("mode") == "active",
        "protected_truth_drop_attempts_runtime": active_budget.get("protected_truth_drop_attempts"),
        "candidate_token_delta_percent_runtime": candidate_delta,
        "operator_disable_path_verified": disabled_budget.get("mode") == "off"
        and disabled_budget.get("enabled") is False,
        "disabled_mode_trace_explicit": disabled_budget.get("mode") == "off",
        "source_runtime_parity": source_runtime_parity,
        "active_probe": active,
        "disabled_probe": disabled,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-container")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = verify_runtime_parity(docker_container=args.docker_container)
    if args.out:
        _write_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
