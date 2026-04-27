from __future__ import annotations

from scripts.ga_product_matrix import redact_private_text, security_privacy_approval_report


def test_ga_security_private_path_redaction() -> None:
    redacted = redact_private_text("/home/lauratom/private/file.txt")

    assert "/home/lauratom" not in redacted
    assert "[REDACTED_PATH]" in redacted


def test_ga_secret_shaped_data_not_model_facing() -> None:
    redacted = redact_private_text("sk-abcdefghi123456")

    assert "sk-abcdefghi123456" not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_ga_security_approval_report_blocks_bypass() -> None:
    payload, md = security_privacy_approval_report()

    assert payload["approval_bypass"] is False
    assert payload["destructive_tool_requires_approval"] is True
    assert "Approval bypass: False" in md
