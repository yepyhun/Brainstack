#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.diagnostics import build_backend_parity_probe, build_query_inspect  # noqa: E402
from brainstack.operating_truth import OPERATING_RECORD_ACTIVE_WORK  # noqa: E402


def _open_store(
    profile_dir: Path,
    *,
    graph_backend: str,
    corpus_backend: str,
) -> BrainstackStore:
    profile_dir.mkdir(parents=True, exist_ok=True)
    store = BrainstackStore(
        str(profile_dir / "brainstack.db"),
        graph_backend=graph_backend,
        graph_db_path=str(profile_dir / "brainstack.kuzu") if graph_backend != "sqlite" else None,
        corpus_backend=corpus_backend,
        corpus_db_path=str(profile_dir / "brainstack.chroma") if corpus_backend != "sqlite" else None,
    )
    store.open()
    return store


def _seed_profile(store: BrainstackStore, *, profile_name: str, token: str) -> str:
    principal_scope_key = f"principal:{profile_name}"
    metadata = {"principal_scope_key": principal_scope_key, "semantic_terms": [token]}
    store.upsert_profile_item(
        stable_key=f"preference:{profile_name}",
        category="preference",
        content=f"{profile_name} profile recall marker {token}.",
        source="enabled-backend-proof.fixture",
        confidence=0.99,
        metadata=metadata,
    )
    store.upsert_operating_record(
        stable_key=f"work:{profile_name}",
        principal_scope_key=principal_scope_key,
        record_type=OPERATING_RECORD_ACTIVE_WORK,
        content=f"{profile_name} operating recall marker {token}.",
        owner="profile_fixture",
        source="enabled-backend-proof.fixture",
        metadata=metadata,
    )
    store.upsert_graph_state(
        subject_name=f"{profile_name} Graph",
        attribute="marker",
        value_text=token,
        source="enabled-backend-proof.fixture",
        metadata=metadata,
    )
    store.ingest_corpus_source(
        {
            "source_adapter": "enabled_backend_proof_fixture",
            "source_id": f"{profile_name}-document",
            "stable_key": f"doc:enabled-backend-proof:{profile_name}",
            "title": f"{profile_name} Backend Proof",
            "doc_kind": "proof_fixture",
            "source_uri": f"fixture://enabled-backend-proof/{profile_name}",
            "content": f"{profile_name} corpus recall marker {token}.",
            "metadata": {"principal_scope_key": principal_scope_key},
        }
    )
    return principal_scope_key


def _selected_count(inspect: Mapping[str, Any]) -> int:
    evidence = inspect.get("selected_evidence") if isinstance(inspect.get("selected_evidence"), Mapping) else {}
    return sum(len(rows) for rows in evidence.values() if isinstance(rows, list))


def _run_profile_probe(
    profile_dir: Path,
    *,
    profile_name: str,
    own_token: str,
    other_token: str,
    graph_backend: str,
    corpus_backend: str,
) -> dict[str, Any]:
    store = _open_store(profile_dir, graph_backend=graph_backend, corpus_backend=corpus_backend)
    try:
        principal_scope_key = _seed_profile(store, profile_name=profile_name, token=own_token)
        own_query = f"{own_token} recall marker"
        probe = build_backend_parity_probe(
            store,
            query=own_query,
            session_id=f"{profile_name}-enabled-backend-proof",
            principal_scope_key=principal_scope_key,
        )
        leak_inspect = build_query_inspect(
            store,
            query=other_token,
            session_id=f"{profile_name}-cross-profile-proof",
            principal_scope_key=principal_scope_key,
            corpus_limit=4,
            graph_limit=6,
        )
        leak_count = _selected_count(leak_inspect)
        selected_counts = dict(probe.get("selected_counts") or {})
        required_missing = [
            shelf
            for shelf in ("profile", "operating", "graph", "corpus")
            if int(selected_counts.get(shelf) or 0) <= 0
        ]
        return {
            "profile": profile_name,
            "public_safe": True,
            "selected_counts": selected_counts,
            "row_counts": dict(probe.get("row_counts") or {}),
            "graph_projection": dict(probe.get("graph_projection") or {}),
            "semantic_corpus_contract": {
                "status": str(dict(probe.get("semantic_corpus_contract") or {}).get("status") or ""),
                "reason_code": str(dict(probe.get("semantic_corpus_contract") or {}).get("reason_code") or ""),
            },
            "required_shelves_missing": required_missing,
            "cross_profile_selected_count": leak_count,
            "cross_profile_bleed_detected": leak_count > 0,
            "capability_verdict": str(dict(probe.get("capability_health") or {}).get("verdict") or ""),
        }
    finally:
        store.close()


def run_proof(root: Path, *, graph_backend: str, corpus_backend: str) -> dict[str, Any]:
    alpha = _run_profile_probe(
        root / "alpha",
        profile_name="alpha",
        own_token="alphaprime42",
        other_token="betaprime91",
        graph_backend=graph_backend,
        corpus_backend=corpus_backend,
    )
    beta = _run_profile_probe(
        root / "beta",
        profile_name="beta",
        own_token="betaprime91",
        other_token="alphaprime42",
        graph_backend=graph_backend,
        corpus_backend=corpus_backend,
    )
    profiles = [alpha, beta]
    missing = any(profile["required_shelves_missing"] for profile in profiles)
    bleed = any(profile["cross_profile_bleed_detected"] for profile in profiles)
    degraded = any(profile["capability_verdict"] == "degraded" for profile in profiles)
    status = "fail" if missing or bleed else ("degraded" if degraded else "pass")
    return {
        "schema": "brainstack.enabled_backend_multiprofile_recall_proof.v1",
        "public_safe": True,
        "status": status,
        "backend_config": {"graph_backend": graph_backend, "corpus_backend": corpus_backend},
        "profiles": profiles,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify multi-profile recall parity for enabled Brainstack backends.")
    parser.add_argument("--workspace-dir", default="")
    parser.add_argument("--graph-backend", default="sqlite")
    parser.add_argument("--corpus-backend", default="sqlite")
    args = parser.parse_args()

    if args.workspace_dir:
        report = run_proof(Path(args.workspace_dir), graph_backend=args.graph_backend, corpus_backend=args.corpus_backend)
    else:
        with tempfile.TemporaryDirectory(prefix="brainstack-enabled-backend-proof-") as temp_dir:
            report = run_proof(Path(temp_dir), graph_backend=args.graph_backend, corpus_backend=args.corpus_backend)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] in {"pass", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
