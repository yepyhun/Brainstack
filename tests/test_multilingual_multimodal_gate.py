from __future__ import annotations

from pathlib import Path
import json

from brainstack import BrainstackMemoryProvider
from brainstack.modality_contract import MODALITY_EVIDENCE_SCHEMA_VERSION, validate_modality_evidence_payload
from scripts.brainstack_multilingual_multimodal_gate import run_multilingual_multimodal_gate


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "multilingual-gate",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def test_explicit_capture_recalls_non_latin_profile_without_locale_phrase_rules(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "identity:chinese-term",
                    "category": "identity",
                    "content": "用户称 Brainstack 为 记忆内核。",
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.98,
                },
            )
        )
        assert receipt["status"] == "committed"

        recall = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "记忆内核"}))
        assert any(
            row["stable_key"] == "identity:chinese-term"
            for row in recall["selected_evidence"]["profile"]
        )
    finally:
        provider.shutdown()


def test_modality_contract_accepts_references_and_rejects_raw_payloads() -> None:
    accepted = validate_modality_evidence_payload(
        {
            "schema": MODALITY_EVIDENCE_SCHEMA_VERSION,
            "modality": "image",
            "source_ref": "fixture://image/diagram",
            "content_hash": "sha256:diagram",
        }
    )
    rejected = validate_modality_evidence_payload(
        {
            "schema": MODALITY_EVIDENCE_SCHEMA_VERSION,
            "modality": "audio",
            "source_ref": "fixture://audio/raw",
            "content_hash": "sha256:audio",
            "base64": "not-allowed",
        }
    )

    assert accepted["status"] == "accepted"
    assert rejected["status"] == "rejected"
    assert rejected["reason"] == "raw_payload_not_allowed"


def test_multilingual_multimodal_gate_reports_language_coverage_and_truthful_modality_status() -> None:
    report = run_multilingual_multimodal_gate()

    assert report["verdict"] == "pass"
    assert report["language_results"]["english"]["passed"]
    assert report["language_results"]["hungarian"]["passed"]
    assert report["language_results"]["german"]["passed"]
    assert report["language_results"]["non_latin"]["passed"]
    assert report["modality_contract"]["passed"]
    assert report["scorecard"]["brainstack"]["full_multimodal_extraction"] == "deferred_not_claimed"
    assert report["latency_ms"] < 10_000
