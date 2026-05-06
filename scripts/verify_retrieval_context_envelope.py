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

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.source_sync_spine import SourceSyncConfig, run_source_sync  # noqa: E402
from scripts.verify_projection_semantics_runtime_parity import _brainstack_stats_stale_correction_events  # noqa: E402


PRINCIPAL_SCOPE = "principal:retrieval-envelope-verifier"


def _packet(store: BrainstackStore, query: str, **signals: object) -> dict[str, Any]:
    return build_working_memory_packet(
        store,
        query=query,
        session_id="session:retrieval-envelope-verifier",
        principal_scope_key=PRINCIPAL_SCOPE,
        profile_match_limit=2,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=2,
        transcript_char_budget=400,
        evidence_item_budget=4,
        graph_limit=2,
        corpus_limit=2,
        corpus_char_budget=400,
        record_retrievals=False,
        adaptive_route_signals=dict(signals),
    )


def run_probe() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-retrieval-envelope-") as temp:
        tmp = Path(temp)
        store = BrainstackStore(str(tmp / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            for event in _brainstack_stats_stale_correction_events():
                copied = json.loads(json.dumps(event))
                copied.setdefault("scope", {})["principal_scope_key"] = PRINCIPAL_SCOPE
                store.record_canonical_memory_event(copied)
            current_packet = _packet(store, "structured current truth request", required_evidence_classes=["current_truth"])
            current_env = current_packet["retrieval_context_envelope"]

            root = tmp / "private-docs"
            root.mkdir()
            (root / "source.md").write_text("# Source\n\nRetrievalEnvelopeVerifierAnchor.", encoding="utf-8")
            run_source_sync(
                store,
                SourceSyncConfig(
                    source_root=root,
                    allow_patterns=("*.md",),
                    source_set_id=str(root),
                    principal_scope_key=PRINCIPAL_SCOPE,
                ),
            )
            corpus_packet = _packet(store, "RetrievalEnvelopeVerifierAnchor", required_evidence_classes=["corpus"])
            corpus_env = corpus_packet["retrieval_context_envelope"]
            no_memory_packet = _packet(store, "", memory_intent="none")
            no_memory_env = no_memory_packet["retrieval_context_envelope"]
            combined = f"{current_packet['block']} {current_env} {corpus_packet['block']} {corpus_env} {no_memory_env}"

            if current_env.get("route_class") != "current_truth":
                issues.append({"code": "current_truth_route_missing", "observed": current_env.get("route_class")})
            if current_env.get("evidence_counts", {}).get("current_truth") != 1:
                issues.append({"code": "current_truth_count_missing"})
            if current_env.get("evidence_counts", {}).get("stale_prior_conflict") != 1:
                issues.append({"code": "stale_prior_count_missing"})
            if corpus_env.get("source_sync", {}).get("expand_handles") != 1:
                issues.append({"code": "source_sync_expand_handle_missing"})
            if no_memory_env.get("semantic_retrieval", {}).get("enabled") is not False:
                issues.append({"code": "no_memory_semantic_enabled"})
            if str(root) in combined or "private-docs" in combined:
                issues.append({"code": "private_path_leaked"})
            if PRINCIPAL_SCOPE in combined:
                issues.append({"code": "private_scope_leaked"})

            return {
                "schema": "brainstack.retrieval_context_envelope_verifier.v1",
                "status": "pass" if not issues else "fail",
                "issues": issues,
                "public_safe": True,
                "current_route": current_env.get("route_class"),
                "current_truth_count": current_env.get("evidence_counts", {}).get("current_truth"),
                "stale_prior_conflict_count": current_env.get("evidence_counts", {}).get("stale_prior_conflict"),
                "corpus_route": corpus_env.get("route_class"),
                "source_expand_handles": corpus_env.get("source_sync", {}).get("expand_handles"),
                "no_memory_route": no_memory_env.get("route_class"),
                "no_memory_semantic_enabled": no_memory_env.get("semantic_retrieval", {}).get("enabled"),
                "raw_private_payload_in_envelope": current_env.get("raw_private_payload_in_envelope") is True
                or corpus_env.get("raw_private_payload_in_envelope") is True,
                "raw_private_scope_in_envelope": PRINCIPAL_SCOPE in combined,
            }
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack RetrievalContextEnvelope behavior.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_probe()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
