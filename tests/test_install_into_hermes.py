from pathlib import Path

from scripts.install_into_hermes import _write_docker_start_script


def test_generated_start_script_carries_full_purge_and_reset_actions(tmp_path: Path):
    script_path = _write_docker_start_script(tmp_path, dry_run=False)
    content = script_path.read_text(encoding="utf-8")

    assert "purge_runtime_state()" in content
    assert "rm -rf /opt/data/sessions /opt/data/memories" in content
    assert "purge|clear-memory|clear-state)" in content
    assert "reset)" in content
    assert "Usage: $0 [start|rebuild|full|stop|purge|reset|status|logs]" in content
