# ruff: noqa: E402
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_host_shims_path = REPO_ROOT / "tests" / "_host_import_shims.py"
_host_shims_spec = importlib.util.spec_from_file_location("phase30_1_document_pipeline_host_import_shims", _host_shims_path)
assert _host_shims_spec and _host_shims_spec.loader
_host_shims = importlib.util.module_from_spec(_host_shims_spec)
_host_shims_spec.loader.exec_module(_host_shims)
install_host_import_shims = _host_shims.install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.db import BrainstackStore
from brainstack.document_pipeline import build_offline_document_pilot


def test_offline_document_pilot_builds_chunks_claims_and_evidence_spans():
    content = (
        "# Overview\n"
        "Brainstack is integrated into Hermes Assistant.\n\n"
        "# Status\n"
        "The current operating-context slice is active.\n"
        "Brainstack remains context-only for reminders.\n"
    )
    pilot = build_offline_document_pilot(
        title="Brainstack rollout note",
        content=content,
        claim_candidates=[
            {
                "subject": "Brainstack",
                "predicate": "integrated_into",
                "object_value": "Hermes Assistant",
                "evidence_snippet": "Brainstack is integrated into Hermes Assistant.",
            },
            {
                "subject": "Brainstack",
                "predicate": "reminder_scope",
                "object_value": "context_only",
                "evidence_snippet": "Brainstack remains context-only for reminders.",
            },
        ],
    )

    assert pilot.offline_only is True
    assert pilot.document.title == "Brainstack rollout note"
    assert pilot.document.section_count == 2
    assert pilot.document.chunk_count >= 2
    assert len(pilot.evidence_spans) == 2
    assert len(pilot.claims) == 2
    assert pilot.claims[0].chunk_id == pilot.evidence_spans[0].chunk_id
    assert pilot.evidence_spans[0].excerpt == "Brainstack is integrated into Hermes Assistant."


def test_offline_document_pilot_surfaces_conflict_candidates_without_silent_merge():
    content = (
        "# Status\n"
        "Brainstack status is active.\n"
        "Brainstack status is paused.\n"
    )
    pilot = build_offline_document_pilot(
        title="Brainstack conflicting status note",
        content=content,
        claim_candidates=[
            {
                "subject": "Brainstack",
                "predicate": "status",
                "object_value": "active",
                "evidence_snippet": "Brainstack status is active.",
            },
            {
                "subject": "Brainstack",
                "predicate": "status",
                "object_value": "paused",
                "evidence_snippet": "Brainstack status is paused.",
            },
        ],
    )

    assert len(pilot.conflict_candidates) == 1
    conflict = pilot.conflict_candidates[0]
    assert conflict.subject == "Brainstack"
    assert conflict.predicate == "status"
    assert len(conflict.claim_ids) == 2


def test_offline_document_pilot_fails_closed_when_evidence_snippet_is_missing():
    content = "# Status\nBrainstack status is active.\n"

    try:
        build_offline_document_pilot(
            title="Brainstack missing evidence note",
            content=content,
            claim_candidates=[
                {
                    "subject": "Brainstack",
                    "predicate": "status",
                    "object_value": "paused",
                    "evidence_snippet": "Brainstack status is paused.",
                }
            ],
        )
    except ValueError as exc:
        assert "Could not locate evidence snippet" in str(exc)
    else:
        raise AssertionError("Expected missing evidence snippet to fail closed.")


def test_offline_document_pilot_does_not_mutate_live_brainstack_store(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()

    pilot = build_offline_document_pilot(
        title="Offline pilot only",
        content="# Note\nBrainstack stays separate from the live graph path.\n",
        claim_candidates=[
            {
                "subject": "Brainstack",
                "predicate": "graph_boundary",
                "object_value": "offline_only",
                "evidence_snippet": "Brainstack stays separate from the live graph path.",
            }
        ],
    )

    assert pilot.document.chunk_count >= 1
    assert store.list_profile_items(limit=10) == []
    assert store.search_graph(query="Brainstack", limit=10) == []
    assert store.search_corpus(query="Brainstack", limit=10) == []
