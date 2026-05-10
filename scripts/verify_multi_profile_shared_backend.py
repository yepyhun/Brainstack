#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.multi_profile_shared_backend import (  # noqa: E402
    build_memory_conflict_primitive,
    build_multi_profile_support_verdict,
    profile_scope_from_kwargs,
)
from brainstack.shelf_export import export_shelf_bundle  # noqa: E402
from brainstack.source_sync_spine import SourceSyncConfig, build_source_sync_status, run_source_sync  # noqa: E402


def _canonical_event(*, event_id: str, principal_scope_key: str) -> dict[str, Any]:
    return {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": "durable_fact_committed",
            "idempotency_key": f"sha256:{event_id}",
        },
        "source": {
            "source_event_id": f"evt_{event_id}",
            "source_span_id": f"span_{event_id}",
            "source_quote_hash": f"sha256:quote_{event_id}",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-05-03T11:58:59Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": principal_scope_key,
            "workspace_scope_key": "workspace:shared",
            "session_id": "session:shared",
        },
        "claim": {
            "memory_kind": "profile",
            "target_slot": "profile.preferred_language",
            "subject_ref": "entity:user:example",
            "predicate": "prefers_language",
            "object_ref": "entity:language:hu",
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"profile:preferred_language:{event_id}",
        },
        "authority": {
            "authority_class": "user_explicit",
            "truth_eligible": True,
            "support_visibility": "answer_evidence",
            "confidence": 0.99,
            "admission_decision_id": f"adm_{event_id}",
            "receipt_id": f"receipt_{event_id}",
        },
        "temporal": {
            "valid_from": "2026-05-03T11:58:00Z",
            "valid_to": "",
            "transaction_time": "2026-05-03T11:59:00Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": ["entity:user:example", "entity:language:hu"],
            "relation_refs": [f"rel:{event_id}"],
            "budget_class": "task_relevant",
            "authority_critical": True,
            "projection_hints": {
                "graph_ready": False,
                "budget_ready": True,
                "multihop_ready": False,
            },
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }


def _provider(tmp: Path, profile: str) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp / "shared" / "brainstack.db"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        f"session-{profile}",
        hermes_home=str(tmp / "hermes-home"),
        platform="discord",
        user_id="user-public",
        agent_identity=profile,
        agent_workspace="shared-home",
        chat_type="dm",
        chat_id="chat-public",
    )
    return provider


def build_report() -> dict[str, Any]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-multiprofile-") as temp:
        tmp = Path(temp)
        profiles = ["researcher", "coder", "sales"]
        scopes = [
            profile_scope_from_kwargs(
                platform="discord",
                user_id="user-public",
                agent_identity=profile,
                agent_workspace="shared-home",
                chat_type="dm",
                chat_id="chat-public",
            )
            for profile in profiles
        ]

        researcher = _provider(tmp, "researcher")
        try:
            assert researcher._store is not None
            researcher._store.upsert_behavior_contract(
                category="style_contract",
                content="Researcher Contract\n\nRules:\n- Researcher-only behavior rule.",
                source="user_explicit:test",
                confidence=0.99,
                metadata=researcher._scoped_metadata({"source_role": "user"}),
            )
            researcher_scope = researcher._principal_scope_key
        finally:
            researcher.shutdown()

        coder = _provider(tmp, "coder")
        try:
            assert coder._store is not None
            behavior_leak = coder._store.get_behavior_contract(principal_scope_key=coder._principal_scope_key)
            coder_scope = coder._principal_scope_key
        finally:
            coder.shutdown()

        store = BrainstackStore(str(tmp / "shared" / "brainstack.db"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            metadata_a = {"principal_scope_key": researcher_scope}
            metadata_b = {"principal_scope_key": coder_scope}
            store.add_continuity_event(
                session_id="shared-session",
                turn_number=1,
                kind="note",
                content="researcher continuity",
                source="test:continuity",
                metadata=metadata_a,
            )
            store.add_continuity_event(
                session_id="shared-session",
                turn_number=2,
                kind="note",
                content="coder continuity",
                source="test:continuity",
                metadata=metadata_b,
            )
            store.upsert_task_item(
                stable_key="task:same-logical",
                principal_scope_key=researcher_scope,
                item_type="task",
                title="researcher task",
                due_date="",
                date_scope="none",
                optional=False,
                status="open",
                owner="test",
                source="test:task",
                metadata=metadata_a,
            )
            store.upsert_task_item(
                stable_key="task:same-logical",
                principal_scope_key=coder_scope,
                item_type="task",
                title="coder task",
                due_date="",
                date_scope="none",
                optional=False,
                status="open",
                owner="test",
                source="test:task",
                metadata=metadata_b,
            )
            store.upsert_operating_record(
                stable_key="operating:same-logical",
                principal_scope_key=researcher_scope,
                record_type="active_work",
                content="researcher operating",
                owner="test",
                source="test:operating",
                metadata=metadata_a,
            )
            store.upsert_operating_record(
                stable_key="operating:same-logical",
                principal_scope_key=coder_scope,
                record_type="active_work",
                content="coder operating",
                owner="test",
                source="test:operating",
                metadata=metadata_b,
            )
            event_a = _canonical_event(event_id="ct_a", principal_scope_key=researcher_scope)
            event_b = _canonical_event(event_id="ct_b", principal_scope_key=coder_scope)
            store.record_canonical_memory_event(event_a)
            store.record_canonical_memory_event(event_b)
            store.upsert_graph_state(
                subject_name="Company A",
                attribute="status",
                value_text="researcher-only",
                source="test:graph",
                metadata=metadata_a,
            )
            store.upsert_graph_state(
                subject_name="Company B",
                attribute="status",
                value_text="coder-only",
                source="test:graph",
                metadata=metadata_b,
            )
            store.ingest_corpus_source(
                {
                    "source_adapter": "test",
                    "source_id": "same-doc",
                    "stable_key": "test:same-doc",
                    "title": "Doc A",
                    "doc_kind": "note",
                    "source_uri": "memory://same-doc",
                    "sections": [{"heading": "A", "content": "researcher corpus"}],
                    "metadata": metadata_a,
                }
            )
            store.ingest_corpus_source(
                {
                    "source_adapter": "test",
                    "source_id": "same-doc",
                    "stable_key": "test:same-doc",
                    "title": "Doc B",
                    "doc_kind": "note",
                    "source_uri": "memory://same-doc",
                    "sections": [{"heading": "B", "content": "coder corpus"}],
                    "metadata": metadata_b,
                }
            )
            store.upsert_proactive_event(
                source="test:proactive",
                kind="proactive_candidate",
                principal_scope_key=researcher_scope,
                title="researcher proactive",
                summary="researcher only",
            )
            store.upsert_proactive_event(
                source="test:proactive",
                kind="proactive_candidate",
                principal_scope_key=coder_scope,
                title="coder proactive",
                summary="coder only",
            )
            source_a = tmp / "source-a"
            source_b = tmp / "source-b"
            source_a.mkdir()
            source_b.mkdir()
            (source_a / "note.md").write_text("researcher source sync", encoding="utf-8")
            (source_b / "note.md").write_text("coder source sync", encoding="utf-8")
            run_source_sync(
                store,
                SourceSyncConfig(
                    source_root=source_a,
                    allow_patterns=("*.md",),
                    source_set_id="shared-source-set",
                    principal_scope_key=researcher_scope,
                ),
            )
            run_source_sync(
                store,
                SourceSyncConfig(
                    source_root=source_b,
                    allow_patterns=("*.md",),
                    source_set_id="shared-source-set",
                    principal_scope_key=coder_scope,
                ),
            )
            bundle = export_shelf_bundle(
                store,
                shelves=("continuity", "operating", "task", "graph", "corpus"),
                principal_scope_key=researcher_scope,
            )
            payload = json.dumps(bundle, ensure_ascii=True)
            current_truth_payload = json.dumps(
                store.get_current_truth_l0_snapshot(principal_scope_key=researcher_scope),
                ensure_ascii=True,
            )
            proactive_payload = json.dumps(store.list_proactive_items(principal_scope_key=researcher_scope), ensure_ascii=True)
            source_sync_status = build_source_sync_status(
                store,
                source_set_id="shared-source-set",
                principal_scope_key=researcher_scope,
            )
        finally:
            store.close()

        missing_identity_verdict = build_multi_profile_support_verdict(
            profile_scopes=[profile_scope_from_kwargs(platform="discord", user_id="user-public")],
            shelf_results={"profile": True},
        )
        conflict = build_memory_conflict_primitive(
            subject="Company A",
            slot="status",
            competing_claim_refs=["claim:researcher", "claim:coder"],
            source_scope_refs=[researcher_scope, coder_scope],
            receipt_refs=["receipt:researcher", "receipt:coder"],
        )
        shelf_results = {
            "profile": behavior_leak is None,
            "continuity": "researcher continuity" in payload and "coder continuity" not in payload,
            "current_truth": "ct_a" in current_truth_payload and "ct_b" not in current_truth_payload,
            "operating": "researcher operating" in payload and "coder operating" not in payload,
            "task": "researcher task" in payload and "coder task" not in payload,
            "graph": "researcher-only" in payload and "coder-only" not in payload,
            "corpus": "researcher corpus" in payload and "coder corpus" not in payload,
            "proactive": "researcher proactive" in proactive_payload and "coder proactive" not in proactive_payload,
            "source_sync": source_sync_status["status"] == "active" and source_sync_status["active_document_count"] == 1,
            "conflict": conflict["current_truth_allowed"] is False,
        }
        verdict = build_multi_profile_support_verdict(profile_scopes=scopes, shelf_results=shelf_results)
        proof = {
            "three_profiles_have_distinct_principal_scopes": len({scope["principal_scope_key"] for scope in scopes}) == 3,
            "missing_profile_identity_degraded": missing_identity_verdict["status"] == "degraded",
            "behavior_contract_no_cross_profile_fallback": behavior_leak is None,
            "continuity_no_cross_profile_bleed": shelf_results["continuity"],
            "current_truth_l0_no_cross_profile_bleed": shelf_results["current_truth"],
            "operating_same_logical_key_no_cross_profile_overwrite": shelf_results["operating"],
            "task_same_logical_key_no_cross_profile_overwrite": shelf_results["task"],
            "graph_export_no_cross_profile_bleed": shelf_results["graph"],
            "corpus_same_logical_key_no_cross_profile_overwrite": shelf_results["corpus"],
            "proactive_no_cross_profile_bleed": shelf_results["proactive"],
            "source_sync_status_no_cross_profile_bleed": shelf_results["source_sync"],
            "conflict_primitive_blocks_current_truth": conflict["current_truth_allowed"] is False,
            "agent_facing_certified_verdict": verdict["status"] == "certified",
        }
        issues = [key for key, value in proof.items() if value is not True]
        return {
            "schema": "brainstack.multi_profile_shared_backend_verifier.v1",
            "status": "pass" if not issues else "fail",
            "public_safe": True,
            "llm_calls_performed": False,
            "issues": issues,
            "proof": proof,
            "support_verdict": verdict,
            "missing_identity_verdict": missing_identity_verdict,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "status", "issues")}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
