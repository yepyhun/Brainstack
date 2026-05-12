from __future__ import annotations

from pathlib import Path

from brainstack.config_shape import validate_brainstack_config_shape
from scripts import brainstack_doctor


def test_valid_flat_profile_isolation_config_passes_shape_guard() -> None:
    report = validate_brainstack_config_shape(
        {
            "plugins": {
                "brainstack": {
                    "db_path": "$HERMES_HOME/brainstack/brainstack.db",
                    "graph_backend": "kuzu",
                    "graph_db_path": "$HERMES_HOME/brainstack/brainstack.kuzu",
                    "corpus_backend": "chroma",
                    "corpus_db_path": "$HERMES_HOME/brainstack/brainstack.chroma",
                }
            }
        }
    )

    assert report["status"] == "pass"
    assert report["issues"] == []
    assert report["flat_storage_keys"]["db_path"] is True


def test_nested_store_paths_are_reported_as_ignored_with_replacements() -> None:
    report = validate_brainstack_config_shape(
        {
            "plugins": {
                "brainstack": {
                    "stores": {
                        "sqlite": {"db_path": "~/profiles/titans/brainstack.db"},
                        "kuzu": {"db_path": "~/profiles/titans/brainstack.kuzu"},
                        "chroma": {"db_path": "~/profiles/titans/brainstack.chroma"},
                    }
                }
            }
        }
    )

    by_path = {issue["key_path"]: issue for issue in report["issues"]}
    assert report["status"] == "fail"
    assert by_path["plugins.brainstack.stores.sqlite.db_path"]["supported_replacement"] == "plugins.brainstack.db_path"
    assert by_path["plugins.brainstack.stores.kuzu.db_path"]["supported_replacement"] == "plugins.brainstack.graph_db_path"
    assert by_path["plugins.brainstack.stores.chroma.db_path"]["supported_replacement"] == "plugins.brainstack.corpus_db_path"
    assert all(issue["runtime_ignored"] for issue in report["issues"])
    assert all(issue["full_isolation_claim_affected"] for issue in report["issues"])


def test_nested_proactive_state_base_is_reported_as_extension_owned() -> None:
    report = validate_brainstack_config_shape(
        {
            "plugins": {
                "brainstack": {
                    "proactive": {"state_base_dir": "~/profiles/titans/brainstack"},
                }
            }
        }
    )

    issue = report["issues"][0]
    assert issue["key_path"] == "plugins.brainstack.proactive.state_base_dir"
    assert issue["supported_replacement"] == "extensions.hermes_proactive.state_base_dir"


def test_doctor_fails_loudly_for_ignored_nested_profile_isolation_config(tmp_path: Path) -> None:
    target = tmp_path / "hermes"
    target.mkdir()
    for relative in (
        "run_agent.py",
        "agent/memory_provider.py",
        "agent/memory_manager.py",
        "plugins/memory/__init__.py",
    ):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    config = target / "config.yaml"
    config.write_text(
        "memory:\n"
        "  provider: brainstack\n"
        "  memory_enabled: true\n"
        "  user_profile_enabled: true\n"
        "plugins:\n"
        "  brainstack:\n"
        "    stores:\n"
        "      sqlite:\n"
        "        db_path: ~/profiles/titans/brainstack.db\n"
        "    proactive:\n"
        "      state_base_dir: ~/profiles/titans/brainstack\n",
        encoding="utf-8",
    )

    checks = brainstack_doctor._check_config(
        config,
        planned_install=True,
        python_bin=None,
        runtime="local",
        compose_path=None,
    )

    failures = [check for check in checks if check.name == "brainstack_config_shape" and check.status == "fail"]
    assert len(failures) >= 2
    assert any("plugins.brainstack.stores.sqlite.db_path" in check.message for check in failures)
    assert any("extensions.hermes_proactive.state_base_dir" in check.message for check in failures)
