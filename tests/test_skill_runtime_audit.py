from __future__ import annotations

from pathlib import Path

from brainstack.skill_runtime_audit import audit_skill_files, validate_skill_view_payload


def test_skill_audit_flags_oversized_entrypoint_without_references(tmp_path: Path) -> None:
    skill = tmp_path / "demo" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("x" * 9000, encoding="utf-8")

    report = audit_skill_files([tmp_path], oversized_chars=8000)

    assert report["verdict"] == "degraded"
    assert report["degraded_count"] == 1
    assert "OVERSIZED_ENTRYPOINT" in report["entries"][0]["reason_codes"]
    assert "NO_REFERENCES_DIR" in report["entries"][0]["reason_codes"]
    assert report["policy"]["auto_rewrite_unknown_skills"] is False


def test_skill_view_payload_validation_requires_progressive_metadata() -> None:
    healthy = validate_skill_view_payload(
        {
            "content_mode": "summary",
            "content_hash": "abc",
            "already_loaded_in_session": True,
            "full_content_available": True,
        }
    )
    degraded = validate_skill_view_payload({"content": "full dump"})

    assert healthy["verdict"] == "healthy"
    assert degraded["verdict"] == "degraded"
    assert set(degraded["missing"]) == {"content_mode", "content_hash", "already_loaded_in_session"}

