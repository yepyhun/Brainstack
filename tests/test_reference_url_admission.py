from __future__ import annotations

from pathlib import Path

from brainstack.product_contracts import admit_reference_url, recall_reference_url
from brainstack.transcript import build_turn_summary, trim_text_boundary


def test_explicit_repo_url_admitted_as_reference_repository_url() -> None:
    record = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
    )

    assert record["target_slot"] == "reference.repository_url"
    assert record["truth_eligible"] is True
    assert record["model_facing_default"] is True


def test_reference_repo_url_exact_recall_after_reset() -> None:
    record = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
    )

    assert recall_reference_url([record], label="resource-x") == "https://example.com/org/resource-x"


def test_transcript_trim_preserves_exact_url_literals() -> None:
    text = (
        "Jegyezd meg ezt repo URL-ként, de ne nyisd meg, mert később pontosan "
        "vissza kell idézni a hivatkozást és a körülötte lévő hosszú magyarázat "
        "szándékosan túlviszi a preview limitet: https://example.com/org/resource-x"
    )

    trimmed = trim_text_boundary(text, max_len=80)

    assert trimmed.endswith("https://example.com/org/resource-x")
    assert "URLs:" in trimmed


def test_turn_summary_preserves_user_url_when_assistant_ack_is_short() -> None:
    summary = build_turn_summary(
        "Jegyezd meg ezt repo URL-ként, de ne nyisd meg: https://example.com/org/resource-x",
        "MEGJEGYEZTEM.",
        max_len=48,
    )

    assert "https://example.com/org/resource-x" in summary


def test_remember_url_does_not_fetch() -> None:
    record = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
    )

    assert record["fetch_on_write"] is False


def test_project_related_repo_requires_resolved_scope() -> None:
    unresolved = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
        as_project_repo_url=True,
    )
    resolved = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
        resolved_project_scope="project:alpha",
    )

    assert unresolved["truth_eligible"] is False
    assert unresolved["reason_code"] == "PROJECT_SCOPE_REQUIRED"
    assert resolved["target_slot"] == "project.related_repo"


def test_project_repo_url_not_confused_with_related_repo() -> None:
    record = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
        resolved_project_scope="project:alpha",
    )

    assert record["target_slot"] == "project.related_repo"
    assert record["target_slot"] != "project.repo_url"


def test_no_hardcoded_memu_nevamind_graphiti() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = ("memU", "NevaMind", "Graphiti")
    hits: list[str] = []
    scanned = (
        root / "brainstack" / "product_contracts.py",
        root / "scripts" / "write_phase183_artifacts.py",
    )
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        if any(item in text for item in forbidden):
            hits.append(str(path.relative_to(root)))

    assert hits == []
