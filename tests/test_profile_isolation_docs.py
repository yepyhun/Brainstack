from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_profile_isolation_guide_points_to_implemented_flags_and_warns_nested_config() -> None:
    doc = (ROOT / "docs" / "INSTALL_AND_PROFILE_ISOLATION.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "--profile titans-agent" in doc
    assert "--isolate-brainstack" in doc
    assert "--isolation-mode full-home" in doc
    assert "--isolation-mode path-override" in doc
    assert "plugins.brainstack.db_path" in doc
    assert "extensions.hermes_proactive.state_base_dir" in doc
    assert "Those nested `stores.*` keys are not Brainstack runtime keys" in doc
    assert "docs/INSTALL_AND_PROFILE_ISOLATION.md" in readme
