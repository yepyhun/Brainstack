from __future__ import annotations

from pathlib import Path

from brainstack.tool_output_envelope import build_tool_output_envelope


def test_large_tool_output_gets_preview_and_full_handle(tmp_path: Path) -> None:
    output = "header\n" + ("line\n" * 1000) + "tail error"

    envelope = build_tool_output_envelope(
        tool_name="terminal",
        output=output,
        inline_char_budget=300,
        artifact_threshold_chars=400,
        artifact_dir=tmp_path,
    )

    assert envelope.truncated is True
    assert envelope.omitted_chars > 0
    assert envelope.full_output_ref is not None
    assert Path(envelope.full_output_ref).exists()
    assert "Open full_output_ref" in envelope.expansion_instruction
    assert envelope.error_hint is True
    assert "tail error" in envelope.model_facing_text


def test_tool_output_preview_redacts_secret_shaped_text() -> None:
    envelope = build_tool_output_envelope(
        tool_name="terminal",
        output="token sk-1234567890abcdef should not be shown",
    )

    assert "sk-1234567890abcdef" not in envelope.model_facing_text
    assert "[REDACTED_SECRET_SHAPED]" in envelope.model_facing_text

