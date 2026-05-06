#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.diagnostics import build_memory_kernel_doctor  # noqa: E402
from scripts import install_into_hermes  # noqa: E402


REPORT_SCHEMA = "brainstack.runtime_spine_capability_parity_proof.v1"
SESSION_ID = "runtime-spine-proof"


def _ready_background_tasks() -> dict[str, Any]:
    readiness = {
        "status": "ready",
        "reason_code": "AUXILIARY_ROUTE_READY",
        "effective_provider_label": "primary-provider",
        "effective_model_label": "gpt-5.5",
        "public_safe": True,
        "secret_redacted": True,
    }
    return {
        "brainstack.background_consolidation": {
            "status": "active",
            "provider_label": "main",
            "model_label": "",
            "main_provider_label": "primary-provider",
            "main_model_label": "gpt-5.5",
            "route_readiness": {**readiness, "task_slot": "flush_memories"},
            "fallback_policy": "none",
        },
    }


def _provider(tmp: Path, *, runtime: str = "internal_extractor", extractor: Any = None) -> BrainstackMemoryProvider:
    config: dict[str, Any] = {
        "db_path": str(tmp / "brainstack.sqlite3"),
        "graph_backend": "sqlite",
        "corpus_backend": "sqlite",
        "tier2_runtime": runtime,
        "tier2_mode": "shadow",
        "tier2_transcript_limit": 4,
        "tier2_timeout_seconds": 2,
        "tier2_hindsight_llm_provider": "hermes_managed",
        "tier2_hindsight_llm_model": "gpt-5.5",
        "background_tasks": _ready_background_tasks(),
    }
    if extractor is not None:
        config["_tier2_extractor"] = extractor
    provider = BrainstackMemoryProvider(config)
    provider.initialize(
        SESSION_ID,
        platform="verification",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id=SESSION_ID,
        turn_number=1,
        kind="turn",
        content="User: public verification turn.\nAssistant: acknowledged.",
        source="verification",
        metadata=provider._scoped_metadata(),
    )
    return provider


def _default_runtime_probe(tmp: Path) -> dict[str, Any]:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp / "default.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        SESSION_ID,
        platform="verification",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    try:
        route = provider.lifecycle_status().get("tier2_runtime_route", {})
        doctor = provider.memory_kernel_doctor(strict=True)
        return {
            "runtime": route.get("runtime"),
            "actual_worker_path": route.get("actual_worker_path"),
            "binding_status": route.get("binding_status"),
            "runtime_invoked_by_worker": route.get("runtime_invoked_by_worker"),
            "configured_runtime_equals_worker_path": route.get("configured_runtime_equals_worker_path"),
            "doctor_verdict": doctor.get("verdict"),
            "tier2_reason_code": doctor.get("capabilities", {}).get("tier2", {}).get("reason_code"),
        }
    finally:
        provider.shutdown()


def _explicit_hindsight_unbound_probe(tmp: Path) -> dict[str, Any]:
    provider = _provider(tmp, runtime="hindsight_public_api_bridge")
    try:
        route = provider.lifecycle_status().get("tier2_runtime_route", {})
        result = provider._run_tier2_batch(
            session_id=SESSION_ID,
            turn_number=1,
            trigger_reason="runtime_spine_unbound_probe",
        )
        doctor = provider.memory_kernel_doctor(strict=True)
        return {
            "runtime": route.get("runtime"),
            "actual_worker_path": route.get("actual_worker_path"),
            "binding_status": route.get("binding_status"),
            "runtime_invoked_by_worker": route.get("runtime_invoked_by_worker"),
            "configured_runtime_equals_worker_path": route.get("configured_runtime_equals_worker_path"),
            "run_status": result.get("status"),
            "request_status": result.get("request_status"),
            "error_recorded": bool(str(result.get("error_reason") or "").strip()),
            "doctor_verdict": doctor.get("verdict"),
            "tier2_reason_code": doctor.get("capabilities", {}).get("tier2", {}).get("reason_code"),
        }
    finally:
        provider.shutdown()


def _explicit_capture_reconcile_probe(tmp: Path) -> dict[str, Any]:
    def extractor(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "profile_items": [
                {
                    "slot": "identity:preferred_address_name",
                    "content": "PublicVerifier",
                    "confidence": 0.95,
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "runtime_spine_probe"},
        }

    provider = _provider(tmp, runtime="internal_extractor", extractor=extractor)
    try:
        trace = provider._validate_explicit_capture_receipts(
            user_content="Remember that my preferred address name is PublicVerifier.",
            session_id=SESSION_ID,
        )
        tier2 = trace.get("tier2") if isinstance(trace.get("tier2"), dict) else {}
        return {
            "status": trace.get("status"),
            "reason_code": trace.get("reason_code"),
            "tier2_status": tier2.get("status"),
            "reconcile_error_present": bool(tier2.get("reconcile_error")),
            "writes_performed_present": "writes_performed" in tier2,
            "consolidation_plan_present": "consolidation_plan" in tier2,
            "receipt_count": len(trace.get("memory_write_receipts") or []),
        }
    finally:
        provider.shutdown()


def _corrupt_corpus_probe(tmp: Path, *, source_rows: bool) -> dict[str, Any]:
    store = BrainstackStore(str(tmp / ("corrupt-source.sqlite3" if source_rows else "corrupt-empty.sqlite3")))
    store.open()
    try:
        if source_rows:
            doc_id = store.upsert_corpus_document(
                stable_key="public-doc",
                title="Public Doc",
                doc_kind="verification",
                source="verification",
            )
            assert int(doc_id) > 0
            store.replace_corpus_sections(
                document_id=int(doc_id),
                title="Public Doc",
                sections=[{"heading": "Overview", "content": "Public verification content."}],
            )
        store._corpus_backend_name = "chroma"
        store._corpus_backend = None
        store._corpus_backend_error = "sqlite3.DatabaseError: file is not a database"
        doctor = build_memory_kernel_doctor(store, strict=True, tier2_state={"enabled": False, "running": False})
        corpus = doctor.get("capabilities", {}).get("corpus", {})
        health = doctor.get("backend_health", {}).get("backends", {}).get("corpus", {})
        repair = corpus.get("repair_plan") if isinstance(corpus.get("repair_plan"), dict) else {}
        return {
            "doctor_verdict": doctor.get("verdict"),
            "corpus_status": corpus.get("status"),
            "error_class": corpus.get("error_class"),
            "health_reason_code": health.get("reason_code"),
            "repair_status": repair.get("status"),
            "repair_reason_code": repair.get("reason_code"),
            "auto_rebuild_allowed": repair.get("auto_rebuild_allowed"),
            "document_count": repair.get("document_count"),
            "section_count": repair.get("section_count"),
        }
    finally:
        store.close()


def _installer_default_probe(tmp: Path) -> dict[str, Any]:
    config = tmp / "config.yaml"
    config.write_text("{}", encoding="utf-8")
    install_into_hermes._patch_config(config, dry_run=False, embedding_runtime="none")
    data = install_into_hermes._load_yaml(config)
    brainstack = data.get("plugins", {}).get("brainstack", {})
    return {
        "tier2_runtime": brainstack.get("tier2_runtime"),
        "tier2_mode": brainstack.get("tier2_mode"),
        "corpus_backend": brainstack.get("corpus_backend"),
        "background_consolidation_status": brainstack.get("background_tasks", {})
        .get("brainstack.background_consolidation", {})
        .get("status"),
    }


def _similar_bug_audit() -> dict[str, Any]:
    files = {
        "inspection": ROOT / "brainstack/provider/inspection.py",
        "tier2_worker": ROOT / "brainstack/provider/tier2_worker.py",
        "installer": ROOT / "scripts/install_into_hermes.py",
    }
    text = {name: path.read_text(encoding="utf-8") for name, path in files.items()}
    return {
        "stale_three_value_reconcile_unpack_present": (
            "action_counts, writes_performed, operating_promotions = reconcile" in text["inspection"]
        ),
        "tier2_reconcile_result_type_present": "Tier2ReconcileResult" in text["tier2_worker"],
        "installer_default_unbound_present": (
            'tier2_runtime", "hindsight_public_api_bridge' in text["installer"]
        ),
        "public_safe": True,
    }


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-runtime-spine-") as temp:
        tmp = Path(temp)
        default_runtime = _default_runtime_probe(tmp)
        unbound = _explicit_hindsight_unbound_probe(tmp)
        explicit_capture = _explicit_capture_reconcile_probe(tmp)
        corrupt_empty = _corrupt_corpus_probe(tmp, source_rows=False)
        corrupt_with_source = _corrupt_corpus_probe(tmp, source_rows=True)
        installer = _installer_default_probe(tmp)
        similar = _similar_bug_audit()

    checks = {
        "default_runtime_bound_internal": default_runtime.get("runtime") == "internal_extractor"
        and default_runtime.get("actual_worker_path") == "internal_extractor"
        and default_runtime.get("binding_status") == "bound"
        and default_runtime.get("configured_runtime_equals_worker_path") is True,
        "explicit_hindsight_unbound_fails_closed": unbound.get("binding_status") == "configured_unbound"
        and unbound.get("run_status") == "failed"
        and unbound.get("request_status") == "failed"
        and unbound.get("error_recorded") is True
        and unbound.get("tier2_reason_code") == "TIER2_RUNTIME_CONFIGURED_UNBOUND",
        "explicit_capture_uses_typed_reconcile_result": explicit_capture.get("reconcile_error_present") is False
        and explicit_capture.get("writes_performed_present") is True
        and explicit_capture.get("consolidation_plan_present") is True,
        "corrupt_empty_corpus_repairable_without_source_delete": corrupt_empty.get("health_reason_code")
        == "BACKEND_STORE_CORRUPT"
        and corrupt_empty.get("repair_status") == "repairable_empty_cache"
        and corrupt_empty.get("auto_rebuild_allowed") is True,
        "corrupt_source_corpus_requires_source_replay": corrupt_with_source.get("health_reason_code")
        == "BACKEND_STORE_CORRUPT"
        and corrupt_with_source.get("repair_status") == "source_replay_required"
        and corrupt_with_source.get("auto_rebuild_allowed") is False,
        "installer_default_not_unbound": installer.get("tier2_runtime") == "internal_extractor",
        "similar_bug_audit_clean": similar.get("stale_three_value_reconcile_unpack_present") is False
        and similar.get("tier2_reconcile_result_type_present") is True
        and similar.get("installer_default_unbound_present") is False,
    }
    issues = [name for name, passed in checks.items() if not passed]
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "llm_calls_performed": False,
        "issues": issues,
        "proof": checks,
        "default_runtime_probe": default_runtime,
        "explicit_hindsight_unbound_probe": unbound,
        "explicit_capture_reconcile_probe": explicit_capture,
        "corrupt_empty_corpus_probe": corrupt_empty,
        "corrupt_source_corpus_probe": corrupt_with_source,
        "installer_default_probe": installer,
        "similar_bug_audit": similar,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
