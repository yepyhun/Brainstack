"""Brainstack plugin config-shape validation.

Brainstack's provider config is intentionally flat. This module catches
plausible nested isolation keys that Hermes/YAML will accept but Brainstack
runtime would ignore.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


CONFIG_SHAPE_SCHEMA = "brainstack.config_shape.v1"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _get_path(root: Mapping[str, Any], parts: tuple[str, ...]) -> Any:
    current: Any = root
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _has_path(root: Mapping[str, Any], parts: tuple[str, ...]) -> bool:
    current: Any = root
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def _issue(
    *,
    key_path: str,
    replacement: str,
    reason_code: str = "UNSUPPORTED_NESTED_BRAINSTACK_CONFIG",
) -> dict[str, Any]:
    return {
        "key_path": key_path,
        "status": "fail",
        "reason_code": reason_code,
        "runtime_ignored": True,
        "full_isolation_claim_affected": True,
        "supported_replacement": replacement,
        "message": (
            f"{key_path} is not a supported Brainstack config key and is ignored by "
            f"runtime. Use {replacement} instead."
        ),
    }


def validate_brainstack_config_shape(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a public-safe validation report for a full Hermes config object."""

    plugins = _as_mapping(config.get("plugins"))
    brainstack = _as_mapping(plugins.get("brainstack"))
    issues: list[dict[str, Any]] = []

    if _has_path(brainstack, ("stores",)):
        issues.append(
            _issue(
                key_path="plugins.brainstack.stores",
                replacement=(
                    "flat plugins.brainstack.db_path / graph_db_path / corpus_db_path"
                ),
            )
        )
    for store_name, replacement in (
        ("sqlite", "plugins.brainstack.db_path"),
        ("kuzu", "plugins.brainstack.graph_db_path"),
        ("chroma", "plugins.brainstack.corpus_db_path"),
    ):
        if _has_path(brainstack, ("stores", store_name)):
            issues.append(
                _issue(
                    key_path=f"plugins.brainstack.stores.{store_name}",
                    replacement=replacement,
                )
            )
        if _has_path(brainstack, ("stores", store_name, "db_path")):
            issues.append(
                _issue(
                    key_path=f"plugins.brainstack.stores.{store_name}.db_path",
                    replacement=replacement,
                )
            )

    if _has_path(brainstack, ("proactive", "state_base_dir")):
        issues.append(
            _issue(
                key_path="plugins.brainstack.proactive.state_base_dir",
                replacement="extensions.hermes_proactive.state_base_dir",
            )
        )

    flat_keys = {
        "db_path": bool(brainstack.get("db_path")),
        "graph_db_path": bool(brainstack.get("graph_db_path")),
        "corpus_db_path": bool(brainstack.get("corpus_db_path")),
    }
    return {
        "schema": CONFIG_SHAPE_SCHEMA,
        "status": "fail" if issues else "pass",
        "issue_count": len(issues),
        "issues": issues,
        "flat_storage_keys": flat_keys,
        "supported_storage_shape": "flat",
    }


def default_profile_brainstack_dir(config_path: Path) -> Path:
    return config_path.expanduser().resolve().parent / "brainstack"
