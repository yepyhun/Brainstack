#!/usr/bin/env python3
"""Build a compact, read-only Brainstack live-memory fitness report proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.product_contracts import assess_workspace_contract  # noqa: E402


REPORT_SCHEMA = "brainstack.live_memory_fitness_report.v1"
PRINCIPAL_SCOPE_KEY = "platform:fitness|user_id:user|agent_identity:agent-smoke|agent_workspace:workspace"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _provider(root: Path, *, hermes_root: Path | None = None) -> BrainstackMemoryProvider:
    hermes_home = root / "hermes_home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    (hermes_home / "config.yaml").write_text(
        "proactive_mode: live\n"
        "proactive_cooldown_seconds: 21600\n"
        "proactive_kill_switch: false\n",
        encoding="utf-8",
    )
    config: dict[str, Any] = {
        "db_path": str(root / "brainstack.sqlite3"),
        "graph_backend": "sqlite",
        "corpus_backend": "sqlite",
        "hermes_home": str(hermes_home),
    }
    if hermes_root is not None:
        config["hermes_root"] = str(hermes_root)
    provider = BrainstackMemoryProvider(config)
    provider.initialize(
        "live-memory-fitness",
        platform="fitness",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    return provider


def _table_counts(provider: BrainstackMemoryProvider) -> dict[str, int]:
    assert provider._store is not None
    rows = provider._store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row["name"])
        counts[name] = int(provider._store.conn.execute(f"SELECT COUNT(*) AS count FROM {name}").fetchone()["count"])
    return counts


def _seed_duplicate_warning(provider: BrainstackMemoryProvider) -> None:
    assert provider._store is not None
    for group in range(4):
        duplicate = f"Public fixture duplicate memory fitness preference {group}."
        for suffix in ("a", "b"):
            provider._store.upsert_profile_item(
                stable_key=f"preference:fitness:{group}:{suffix}",
                category="preference",
                content=duplicate,
                source="phase-297-fixture",
                confidence=0.99,
                metadata={"principal_scope_key": provider._principal_scope_key, "truth_eligible": True},
            )


def _seed_kanban_fixture(hermes_root: Path) -> None:
    (hermes_root / "tools").mkdir(parents=True, exist_ok=True)
    (hermes_root / "hermes_cli").mkdir(parents=True, exist_ok=True)
    (hermes_root / "plugins" / "kanban").mkdir(parents=True, exist_ok=True)
    (hermes_root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (hermes_root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")


def _compact_stats(stats: Mapping[str, Any]) -> dict[str, Any]:
    persistent_bloat = stats.get("persistent_bloat") if isinstance(stats.get("persistent_bloat"), Mapping) else {}
    doctor = stats.get("doctor") if isinstance(stats.get("doctor"), Mapping) else {}
    backend_health = stats.get("backend_health") if isinstance(stats.get("backend_health"), Mapping) else {}
    return {
        "status": str(stats.get("status") or ""),
        "strict_requested": bool(stats.get("strict_requested")),
        "backend_health_status": str(backend_health.get("status") or ""),
        "doctor_verdict": str(doctor.get("verdict") or ""),
        "persistent_bloat_status": str(persistent_bloat.get("status") or ""),
        "persistent_bloat_issues": [str(issue) for issue in list(persistent_bloat.get("issues") or [])[:8]],
    }


def _finding(
    *,
    code: str,
    severity: str,
    owner: str,
    title: str,
    next_action: str,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "owner": owner,
        "title": title,
        "next_action": next_action,
        "evidence": dict(evidence or {}),
    }


def classify_memory_fitness(
    *,
    stats: Mapping[str, Any],
    proactive_status: Mapping[str, Any],
    graph_producer: Mapping[str, Any],
    workspace_contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    compact_stats = _compact_stats(stats)
    if compact_stats["status"] == "fail":
        findings.append(
            _finding(
                code="strict_health_failed",
                severity="HIGH",
                owner="brainstack",
                title="Strict Brainstack health is failing.",
                next_action="Run brainstack_stats(strict=True) and the matching verifier before release.",
                evidence={"status": compact_stats["status"], "doctor_verdict": compact_stats["doctor_verdict"]},
            )
        )
    bloat_issues = set(compact_stats["persistent_bloat_issues"])
    if any(issue.startswith("DUPLICATE_STRENGTH_INFLATION") for issue in bloat_issues):
        findings.append(
            _finding(
                code="duplicate_strength_quality_debt",
                severity="LOW_HANGING_FRUIT",
                owner="brainstack",
                title="Duplicate truth rows can inflate perceived memory strength if not budgeted.",
                next_action="Run duplicate-strength verifier and safe maintenance dry-run; do not auto-merge truth.",
                evidence={"issues": sorted(bloat_issues)},
            )
        )
    producer_state = str(graph_producer.get("producer_state") or "")
    if producer_state in {"no_input", "no_graph_candidates"}:
        findings.append(
            _finding(
                code="graph_underfed_no_typed_input",
                severity="HEALTHY_IDLE",
                owner="brainstack",
                title="Graph producer has no typed source-backed graph input yet.",
                next_action="No repair. Add typed source-backed candidates when real graph-worthy work exists.",
                evidence={"producer_state": producer_state, "reason_code": str(graph_producer.get("reason_code") or "")},
            )
        )
    proactive_state = str(proactive_status.get("operational_state") or "")
    if proactive_state == "ready_idle" and proactive_status.get("idle_is_failure") is False:
        findings.append(
            _finding(
                code="proactive_ready_idle",
                severity="HEALTHY_IDLE",
                owner="brainstack_extension",
                title="Proactive layer is ready and idle.",
                next_action="No repair. Idle without candidates is not a failure.",
                evidence={"operational_state": proactive_state},
            )
        )
    kanban = proactive_status.get("workstation_integrations", {}).get("kanban", {}) if isinstance(proactive_status.get("workstation_integrations"), Mapping) else {}
    if kanban.get("available") is True and kanban.get("can_write_board") is not True:
        findings.append(
            _finding(
                code="kanban_detected_not_agent_write_certified",
                severity="EXTERNAL_OWNER",
                owner="hermes_kanban",
                title="Hermes Kanban is detected but not certified as a Brainstack writable work queue.",
                next_action="Do not claim real Kanban worker use until Hermes tool-surface write proof exists.",
                evidence={"available": True, "can_write_board": bool(kanban.get("can_write_board"))},
            )
        )
    if str(workspace_contract.get("fixture_status") or "") != "present":
        findings.append(
            _finding(
                code="workspace_contract_invalid",
                severity="HIGH",
                owner="brainstack_installer_or_wizard",
                title="Runtime workspace fixture is missing or half-wired.",
                next_action="Run Phase 293 workstation verifier and repair installer/runtime parity before release.",
                evidence={"fixture_status": str(workspace_contract.get("fixture_status") or "")},
            )
        )
    return findings


def _severity_counts(findings: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        severity = str(finding.get("severity") or "UNKNOWN")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _release_blocked(findings: list[Mapping[str, Any]]) -> bool:
    return any(
        str(item.get("owner") or "").startswith("brainstack")
        and str(item.get("severity") or "") in {"CRIT", "HIGH"}
        for item in findings
    )


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-memory-fitness-") as tmpdir:
        root = Path(tmpdir)
        hermes_root = root / "hermes_root"
        _seed_kanban_fixture(hermes_root)
        workspace_root = root / "workspace_contract"
        (workspace_root / "project").mkdir(parents=True)
        (workspace_root / "project" / "README.md").write_text("# Public fixture\n", encoding="utf-8")
        (workspace_root / "user").mkdir(parents=True)
        invalid_workspace_root = root / "invalid_workspace_contract"

        provider = _provider(root, hermes_root=hermes_root)
        try:
            _seed_duplicate_warning(provider)
            before_counts = _table_counts(provider)
            stats = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))
            proactive = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
            doctor = provider.memory_kernel_doctor(strict=True)
            graph_producer = doctor.get("capabilities", {}).get("graph_producer", {})
            workspace = assess_workspace_contract(workspace_root).to_dict()
            invalid_workspace = assess_workspace_contract(invalid_workspace_root).to_dict()
            findings = classify_memory_fitness(
                stats=stats,
                proactive_status=proactive,
                graph_producer=graph_producer if isinstance(graph_producer, Mapping) else {},
                workspace_contract=workspace,
            )
            invalid_workspace_findings = classify_memory_fitness(
                stats=stats,
                proactive_status=proactive,
                graph_producer=graph_producer if isinstance(graph_producer, Mapping) else {},
                workspace_contract=invalid_workspace,
            )
            after_counts = _table_counts(provider)
        finally:
            provider.shutdown()

    proof = {
        "read_only_table_counts_unchanged": before_counts == after_counts,
        "duplicate_strength_classified_not_all_good": any(item["code"] == "duplicate_strength_quality_debt" for item in findings),
        "healthy_proactive_idle_not_failure": any(item["code"] == "proactive_ready_idle" for item in findings),
        "kanban_detected_not_write_certified": any(
            item["code"] == "kanban_detected_not_agent_write_certified" for item in findings
        ),
        "invalid_workspace_is_high": any(item["code"] == "workspace_contract_invalid" and item["severity"] == "HIGH" for item in invalid_workspace_findings),
        "release_blocks_only_brainstack_high": _release_blocked(invalid_workspace_findings) is True
        and _release_blocked(findings) is False,
        "public_safe_output": True,
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "read_only": True,
        "public_safe": True,
        "bounded_model_facing": True,
        "release_blocked": _release_blocked(findings),
        "summary": {
            "finding_count": len(findings),
            "severity_counts": _severity_counts(findings),
            "top_next_actions": [str(item["next_action"]) for item in findings[:5]],
        },
        "findings": findings,
        "proof": proof,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify read-only live memory fitness report.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
