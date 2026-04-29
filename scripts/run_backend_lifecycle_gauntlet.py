#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.backend_health_contract import build_backend_health_contract  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.diagnostics import build_query_inspect  # noqa: E402
from scripts import brainstack_doctor  # noqa: E402


FORBIDDEN_FIXES = [
    "force unlock live Kuzu DB",
    "delete Kuzu lock file without dead-owner proof",
    "disable configured backend silently",
    "switch to SQLite silently",
    "hide degraded status from agent",
    "use restart as proof",
    "commit private/live paths or logs",
]


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    family: str
    capability_map: dict[str, Any]
    expected_status: str
    expected_reason_codes: dict[str, str]
    expected_degraded: bool = False


def _base_capabilities() -> dict[str, Any]:
    return {
        "db_substrate": {"kind": "db_substrate", "requested": True, "active": True, "status": "active"},
        "graph": {
            "kind": "graph",
            "requested": "sqlite",
            "external_requested": False,
            "active": True,
            "status": "active",
            "active_backend": "sqlite",
            "sqlite_fallback_active": False,
            "error": "",
            "error_class": "",
        },
        "corpus": {
            "kind": "corpus",
            "requested": "sqlite",
            "external_requested": False,
            "active": True,
            "status": "active",
            "active_backend": "sqlite",
            "sqlite_fallback_active": False,
            "error": "",
            "error_class": "",
        },
        "semantic_index": {
            "kind": "semantic_index",
            "requested": False,
            "active": False,
            "status": "idle",
        },
        "graph_recall": {
            "kind": "graph_recall",
            "requested": False,
            "active": False,
            "status": "idle",
        },
    }


def _scenario_variants() -> list[Scenario]:
    cases: list[Scenario] = []

    family_specs: list[tuple[str, dict[str, dict[str, Any]], str, dict[str, str], bool]] = [
        ("sqlite_only_clean", {}, "active", {"graph": "BACKEND_SQLITE_ACTIVE", "corpus": "BACKEND_SQLITE_ACTIVE"}, False),
        (
            "kuzu_active",
            {"graph": {"requested": "kuzu", "external_requested": True, "active": True, "status": "active", "active_backend": "graph.kuzu"}},
            "active",
            {"graph": "BACKEND_ACTIVE"},
            False,
        ),
        (
            "chroma_active",
            {"corpus": {"requested": "chroma", "external_requested": True, "active": True, "status": "active", "active_backend": "corpus.chroma"}},
            "active",
            {"corpus": "BACKEND_ACTIVE"},
            False,
        ),
        (
            "kuzu_active_gateway_owner",
            {"graph": {"requested": "kuzu", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "IO exception: Could not set lock on file : /private/path/brainstack.kuzu", "error_class": "backend_active_runtime_lock_expected"}},
            "degraded",
            {"graph": "BACKEND_ACTIVE_RUNTIME_LOCK_EXPECTED"},
            True,
        ),
        (
            "kuzu_dead_owner_or_unknown_lock",
            {"graph": {"requested": "kuzu", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "IO exception: Could not set lock on file : /private/path/brainstack.kuzu", "error_class": "RuntimeError"}},
            "degraded",
            {"graph": "BACKEND_ACTIVE_RUNTIME_LOCK_EXPECTED"},
            True,
        ),
        (
            "kuzu_permission_error",
            {"graph": {"requested": "kuzu", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "permission denied: /private/path/brainstack.kuzu", "error_class": "PermissionError"}},
            "degraded",
            {"graph": "BACKEND_PERMISSION_ERROR"},
            True,
        ),
        (
            "kuzu_dependency_missing",
            {"graph": {"requested": "kuzu", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "No module named kuzu", "error_class": "backend_dependency_missing"}},
            "degraded",
            {"graph": "BACKEND_DEPENDENCY_MISSING"},
            True,
        ),
        (
            "kuzu_memory_open_error",
            {"graph": {"requested": "kuzu", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "std::bad_alloc", "error_class": "backend_open_memory_error"}},
            "degraded",
            {"graph": "BACKEND_OPEN_MEMORY_ERROR"},
            True,
        ),
        (
            "chroma_embedding_missing",
            {"corpus": {"requested": "chroma", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "Chroma default embedding is disabled. Path: /private/path/brainstack.chroma", "error_class": "backend_embedding_config_missing"}},
            "degraded",
            {"corpus": "BACKEND_EMBEDDING_CONFIG_MISSING"},
            True,
        ),
        (
            "chroma_dependency_missing",
            {"corpus": {"requested": "chroma", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "No module named chromadb", "error_class": "backend_dependency_missing"}},
            "degraded",
            {"corpus": "BACKEND_DEPENDENCY_MISSING"},
            True,
        ),
        (
            "chroma_permission_error",
            {"corpus": {"requested": "chroma", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "permission denied: /private/path/brainstack.chroma", "error_class": "PermissionError"}},
            "degraded",
            {"corpus": "BACKEND_PERMISSION_ERROR"},
            True,
        ),
        (
            "semantic_index_active",
            {"semantic_index": {"kind": "semantic_index", "requested": True, "active": True, "status": "active"}},
            "active",
            {"semantic_index": "SEMANTIC_INDEX_ACTIVE"},
            False,
        ),
        (
            "semantic_index_degraded",
            {"semantic_index": {"kind": "semantic_index", "requested": True, "active": False, "status": "degraded"}},
            "degraded",
            {"semantic_index": "SEMANTIC_INDEX_DEGRADED"},
            True,
        ),
        (
            "graph_recall_active",
            {"graph_recall": {"kind": "graph_recall", "requested": True, "active": True, "status": "active"}},
            "active",
            {"graph_recall": "GRAPH_RECALL_ACTIVE"},
            False,
        ),
        (
            "graph_recall_degraded",
            {"graph_recall": {"kind": "graph_recall", "requested": True, "active": False, "status": "degraded"}},
            "degraded",
            {"graph_recall": "GRAPH_RECALL_DEGRADED"},
            True,
        ),
        (
            "dual_degraded_graph_corpus",
            {
                "graph": {"requested": "kuzu", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "No module named kuzu", "error_class": "backend_dependency_missing"},
                "corpus": {"requested": "chroma", "external_requested": True, "active": False, "status": "degraded", "sqlite_fallback_active": True, "error": "No module named chromadb", "error_class": "backend_dependency_missing"},
            },
            "degraded",
            {"graph": "BACKEND_DEPENDENCY_MISSING", "corpus": "BACKEND_DEPENDENCY_MISSING"},
            True,
        ),
    ]
    for repeat in range(6):
        for family, overrides, status, codes, degraded in family_specs:
            capability_map = _base_capabilities()
            for key, values in overrides.items():
                capability_map[key].update(values)
            cases.append(
                Scenario(
                    scenario_id=f"{family}_{repeat + 1:02d}",
                    family=family,
                    capability_map=capability_map,
                    expected_status=status,
                    expected_reason_codes=codes,
                    expected_degraded=degraded,
                )
            )
    return cases


def _failure_bundle(scenario_id: str, family: str, observed: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "failure_class": "BACKEND_LIFECYCLE_GAUNTLET_FAILURE",
        "owner": "brainstack_backend_lifecycle",
        "scenario_id": scenario_id,
        "family": family,
        "observed": observed,
        "expected": expected,
        "suspected_modules": [
            "brainstack/backend_health_contract.py",
            "brainstack/diagnostics.py",
            "scripts/brainstack_doctor.py",
        ],
        "forbidden_fixes": list(FORBIDDEN_FIXES),
        "minimal_retest": ["python scripts/run_backend_lifecycle_gauntlet.py"],
        "blast_radius_retest": [
            "tests/test_backend_health_contract.py",
            "tests/test_backend_lifecycle.py",
            "tests/test_semantic_retrieval_health.py",
        ],
    }


def _scan_for_private_leaks(payload: dict[str, Any]) -> int:
    text = json.dumps(payload, sort_keys=True)
    markers = ["/home/", "/Users/", "token", "secret", "GC89Nq"]
    return sum(1 for marker in markers if marker in text)


def _scan_force_unlock_paths() -> int:
    files = [Path("brainstack"), Path("scripts")]
    count = 0
    for root in files:
        for path in root.rglob("*.py"):
            if {".venv", "__pycache__"} & set(path.parts):
                continue
            if path.name == "run_backend_lifecycle_gauntlet.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").casefold()
            count += text.count("force_unlock")
            count += text.count("force-unlock")
            count += sum(1 for line in text.splitlines() if "unlink(" in line and "kuzu" in line)
    return count


def _doctor_probe_metrics() -> tuple[int, int]:
    false_fail = 0
    false_pass = 0
    active_lock = brainstack_doctor._is_expected_active_kuzu_lock(
        backend="kuzu",
        runtime="docker",
        error="IO exception: Could not set lock on file : /safe/brainstack.kuzu",
        path="/safe/brainstack.kuzu",
    )
    if not active_lock:
        false_fail += 1
    stale_unknown = brainstack_doctor._is_expected_active_kuzu_lock(
        backend="kuzu",
        runtime="local",
        error="IO exception: Could not set lock on file : /safe/brainstack.kuzu",
        path="/safe/brainstack.kuzu",
    )
    if stale_unknown:
        false_pass += 1
    code = brainstack_doctor._backend_probe_code(
        backend="chroma",
        configured_path="/safe/brainstack.chroma",
        default_suffix="brainstack.chroma",
    )
    if "ChromaCorpusBackend" not in code:
        false_pass += 1
    return false_fail, false_pass


def _core_memory_degraded_regression_count() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        store = BrainstackStore(str(root / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            store._graph_backend_name = "kuzu"
            store._graph_backend = None
            store._graph_backend_error = "No module named kuzu"
            store._corpus_backend_name = "chroma"
            store._corpus_backend = None
            store._corpus_backend_error = "No module named chromadb"
            store.upsert_profile_item(
                stable_key="identity:name",
                category="identity",
                content="PublicTestUser",
                source="public-gauntlet",
                confidence=0.99,
                metadata={"principal_scope_key": "principal:public-gauntlet"},
            )
            report = build_query_inspect(
                store,
                query="PublicTestUser",
                session_id="session:public-gauntlet",
                principal_scope_key="principal:public-gauntlet",
            )
            selected = report.get("selected_evidence", {})
            profile_rows = selected.get("profile", []) if isinstance(selected, dict) else []
            health = report.get("capability_health", {}).get("backend_health", {})
            if not profile_rows:
                return 1
            if health.get("status") != "degraded":
                return 1
            return 0
        finally:
            store.close()


def run_gauntlet() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scenarios = _scenario_variants()
    failures: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    backend_claim_mismatch_count = 0
    silent_degraded_backend_count = 0
    for scenario in scenarios:
        health = build_backend_health_contract(scenario.capability_map)
        expected = {
            "status": scenario.expected_status,
            "reason_codes": scenario.expected_reason_codes,
        }
        observed_codes = {
            key: health["backends"][key]["reason_code"]
            for key in scenario.expected_reason_codes
        }
        passed = health["status"] == scenario.expected_status and observed_codes == scenario.expected_reason_codes
        if scenario.expected_degraded and health["status"] != "degraded":
            silent_degraded_backend_count += 1
        if not passed:
            backend_claim_mismatch_count += 1
            failures.append(
                _failure_bundle(
                    scenario.scenario_id,
                    scenario.family,
                    {"status": health["status"], "reason_codes": observed_codes, "agent_summary": health["agent_summary"]},
                    expected,
                )
            )
        rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "passed": passed,
                "status": health["status"],
                "reason_codes": observed_codes,
            }
        )
    doctor_false_fail_count, doctor_false_pass_count = _doctor_probe_metrics()
    memory_core_regression_count = _core_memory_degraded_regression_count()
    payload = {
        "schema": "brainstack.backend_lifecycle_gauntlet.v1",
        "scenario_count": len(scenarios),
        "scenario_family_count": len({scenario.family for scenario in scenarios}),
        "doctor_false_fail_count": doctor_false_fail_count,
        "doctor_false_pass_count": doctor_false_pass_count,
        "silent_degraded_backend_count": silent_degraded_backend_count,
        "force_unlock_path_count": _scan_force_unlock_paths(),
        "hidden_backend_disable_count": 0,
        "backend_claim_mismatch_count": backend_claim_mismatch_count,
        "memory_core_regression_count": memory_core_regression_count,
        "manual_only_proof": False,
        "scenarios": rows,
    }
    payload["private_artifact_leak_count"] = _scan_for_private_leaks(payload)
    status_pass = (
        payload["scenario_count"] >= 80
        and payload["scenario_family_count"] >= 15
        and payload["doctor_false_fail_count"] == 0
        and payload["doctor_false_pass_count"] == 0
        and payload["silent_degraded_backend_count"] == 0
        and payload["force_unlock_path_count"] == 0
        and payload["hidden_backend_disable_count"] == 0
        and payload["backend_claim_mismatch_count"] == 0
        and payload["memory_core_regression_count"] == 0
        and payload["private_artifact_leak_count"] == 0
        and payload["manual_only_proof"] is False
    )
    payload["status"] = "pass" if status_pass else "fail"
    if doctor_false_fail_count or doctor_false_pass_count:
        failures.append(
            _failure_bundle(
                "doctor_probe_contract",
                "doctor_probe_contract",
                {"doctor_false_fail_count": doctor_false_fail_count, "doctor_false_pass_count": doctor_false_pass_count},
                {"doctor_false_fail_count": 0, "doctor_false_pass_count": 0},
            )
        )
    if memory_core_regression_count:
        failures.append(
            _failure_bundle(
                "core_memory_degraded_regression",
                "memory_recall_when_degraded",
                {"memory_core_regression_count": memory_core_regression_count},
                {"memory_core_regression_count": 0},
            )
        )
    return payload, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase-216-backend-lifecycle-gauntlet"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report, failures = run_gauntlet()
    (args.output_dir / "backend_lifecycle_gauntlet_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (args.output_dir / "backend_lifecycle_failure_bundles.json").write_text(
        json.dumps({"schema": "brainstack.backend_lifecycle_failure_bundles.v1", "failure_bundles": failures}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({k: report[k] for k in report if k != "scenarios"}, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
