from __future__ import annotations

from brainstack.product_contracts import build_capability_manifest


def _status(manifest: dict, capability_id: str) -> str:
    for item in manifest["capabilities"]:
        if item["capability_id"] == capability_id:
            return str(item["status"])
    raise AssertionError(capability_id)


def test_capability_status_vocab() -> None:
    manifest = build_capability_manifest(
        configured_capabilities=("filesystem.search_read", "web.browse"),
        executable_capabilities=("filesystem.search_read",),
        disabled_capabilities=("terminal.execute",),
        unavailable_reasons={"web.browse": "missing_backend_or_env_key"},
    )

    statuses = {item["status"] for item in manifest["capabilities"]}
    assert "configured_available" in statuses
    assert "configured_unavailable" in statuses
    assert "disabled_by_admin" in statuses


def test_web_configured_unavailable_when_backend_missing() -> None:
    manifest = build_capability_manifest(
        configured_capabilities=("web.browse",),
        unavailable_reasons={"web.browse": "missing_backend_or_env_key"},
    )

    assert _status(manifest, "web.browse") == "configured_unavailable"
    assert manifest["capabilities"][0]["reason"] == "missing_backend_or_env_key"


def test_terminal_available_requires_approval_status() -> None:
    manifest = build_capability_manifest(
        configured_capabilities=("terminal.execute",),
        executable_capabilities=("terminal.execute",),
        approval_required_capabilities=("terminal.execute",),
    )

    assert _status(manifest, "terminal.execute") == "configured_available"
    assert manifest["capabilities"][0]["approval_required"] is True

