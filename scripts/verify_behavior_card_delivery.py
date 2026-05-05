from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.active_preference_contract import (  # noqa: E402
    DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION,
    DELIVERY_REASON_SESSION_START,
)
from brainstack.style_contract import STYLE_CONTRACT_SLOT  # noqa: E402


DEFAULT_HERMES_SOURCE = Path("/home/lauratom/Asztal/ai/atado/hermes-latest-source-clean-20260504-003042")


def _rules(count: int = 25) -> list[str]:
    return [f"Rule {index:02d} must survive the Hermes behavior-card seam." for index in range(1, count + 1)]


def _contract_text(lines: list[str]) -> str:
    return "LauraTom behavior card\n\nRules:\n" + "\n".join(f"- {line}" for line in lines)


def _write_style_rules(provider: BrainstackMemoryProvider, lines: list[str]) -> dict[str, Any]:
    payload = provider.handle_tool_call(
        "brainstack_remember",
        {
            "shelf": "profile",
            "stable_key": "preference.discord_response_style_plain_hungarian_2026_05_04",
            "category": "style_preference",
            "content": _contract_text(lines),
            "source_role": "user",
            "authority_class": "profile",
            "confidence": 0.99,
            "metadata": {"target_slot": "preference.discord_response_style"},
        },
    )
    return json.loads(payload)


def _missing_rules(block: str, lines: list[str]) -> list[str]:
    return [line for line in lines if line not in block]


def _trace(provider: BrainstackMemoryProvider) -> dict[str, Any]:
    raw = provider.behavior_policy_trace() or {}
    system_prompt_block = raw.get("system_prompt_block") if isinstance(raw, Mapping) else {}
    delivery = system_prompt_block.get("active_preference_contract_delivery") if isinstance(system_prompt_block, Mapping) else {}
    return dict(delivery or {})


def _load_memory_manager(hermes_source: Path):
    if not hermes_source.exists():
        raise FileNotFoundError(f"Hermes source path not found: {hermes_source}")
    hermes_path = str(hermes_source)
    sys.path = [entry for entry in sys.path if entry != hermes_path]
    sys.path.insert(0, hermes_path)
    loaded_agent = sys.modules.get("agent")
    if loaded_agent is not None and not hasattr(loaded_agent, "__path__"):
        for module_name in [name for name in sys.modules if name == "agent" or name.startswith("agent.")]:
            sys.modules.pop(module_name, None)
    from agent.memory_manager import MemoryManager  # type: ignore

    return MemoryManager


def run(*, hermes_source: Path, out: Path | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    lines = _rules()
    MemoryManager = _load_memory_manager(hermes_source)
    with tempfile.TemporaryDirectory(prefix="brainstack-behavior-card-delivery-") as temp:
        root = Path(temp)
        provider = BrainstackMemoryProvider(
            {
                "db_path": str(root / "brainstack.sqlite3"),
                "graph_backend": "sqlite",
                "corpus_backend": "sqlite",
            }
        )
        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all(
            session_id="behavior-card-session",
            hermes_home=str(root),
            platform="local-proof",
            user_id="user",
            agent_identity="agent-behavior-card",
            agent_workspace="workspace",
        )
        try:
            receipt = _write_style_rules(provider, lines)
            materialized = dict(receipt.get("style_contract_materialization") or {})
            if materialized.get("status") != "materialized":
                issues.append({"stage": "write", "code": "style_contract_not_materialized", "observed": materialized})

            session_start_block = manager.build_system_prompt()
            session_trace = _trace(provider)
            missing_session = _missing_rules(session_start_block, lines)
            if missing_session:
                issues.append({"stage": "session_start", "code": "missing_rules", "missing_count": len(missing_session)})
            if session_trace.get("delivery_reason") != DELIVERY_REASON_SESSION_START:
                issues.append(
                    {
                        "stage": "session_start",
                        "code": "wrong_delivery_reason",
                        "observed": session_trace.get("delivery_reason"),
                    }
                )
            if session_trace.get("delivery_status") != "delivered_full":
                issues.append(
                    {
                        "stage": "session_start",
                        "code": "not_delivered_full",
                        "observed": session_trace.get("delivery_status"),
                    }
                )

            manager.on_pre_compress(
                [
                    {"role": "user", "content": "Start the public-safe delivery proof."},
                    {"role": "assistant", "content": "Continuing the public-safe proof."},
                    {"role": "user", "content": "Trigger compression rebuild proof."},
                ]
            )
            compression_block = manager.build_system_prompt()
            compression_trace = _trace(provider)
            missing_compression = _missing_rules(compression_block, lines)
            if missing_compression:
                issues.append({"stage": "compression", "code": "missing_rules", "missing_count": len(missing_compression)})
            if compression_trace.get("delivery_reason") != DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION:
                issues.append(
                    {
                        "stage": "compression",
                        "code": "wrong_delivery_reason",
                        "observed": compression_trace.get("delivery_reason"),
                    }
                )
            if compression_trace.get("delivery_status") != "delivered_full":
                issues.append(
                    {
                        "stage": "compression",
                        "code": "not_delivered_full",
                        "observed": compression_trace.get("delivery_status"),
                    }
                )

            inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": "active behavior card"}))
            inspect_delivery = dict(inspect.get("report", {}).get("active_preference_delivery") or {})
            if inspect_delivery.get("source_stable_key") != STYLE_CONTRACT_SLOT:
                issues.append(
                    {
                        "stage": "inspect",
                        "code": "source_slot_not_reported",
                        "observed": inspect_delivery.get("source_stable_key"),
                    }
                )
            if inspect_delivery.get("active_rule_count") != 25:
                issues.append(
                    {
                        "stage": "inspect",
                        "code": "rule_count_not_reported",
                        "observed": inspect_delivery.get("active_rule_count"),
                    }
                )

            behavior_rows = provider._store.conn.execute("select count(*) from behavior_contracts").fetchone()[0] if provider._store else -1
            compiled_rows = provider._store.conn.execute("select count(*) from compiled_behavior_policies").fetchone()[0] if provider._store else -1
            if behavior_rows or compiled_rows:
                issues.append(
                    {
                        "stage": "storage",
                        "code": "durable_behavior_rows_created",
                        "behavior_contracts": behavior_rows,
                        "compiled_behavior_policies": compiled_rows,
                    }
                )

            report = {
                "schema": "brainstack.behavior_card_delivery_verifier.v1",
                "status": "pass" if not issues else "fail",
                "issues": issues,
                "hermes_source": str(hermes_source),
                "session_start": {
                    "rule_count": 25 - len(missing_session),
                    "delivery_reason": session_trace.get("delivery_reason"),
                    "delivery_status": session_trace.get("delivery_status"),
                    "source_stable_key": session_trace.get("source_stable_key"),
                    "source_lane": session_trace.get("source_lane"),
                },
                "post_compression": {
                    "rule_count": 25 - len(missing_compression),
                    "delivery_reason": compression_trace.get("delivery_reason"),
                    "delivery_status": compression_trace.get("delivery_status"),
                    "prompt_rebuild_id_present": bool(compression_trace.get("prompt_rebuild_id")),
                    "compaction_event_id_present": bool(compression_trace.get("compaction_event_id")),
                },
                "inspect": {
                    "delivery_status": inspect_delivery.get("delivery_status"),
                    "active_rule_count": inspect_delivery.get("active_rule_count"),
                    "source_stable_key": inspect_delivery.get("source_stable_key"),
                    "source_lane": inspect_delivery.get("source_lane"),
                    "raw_private_text_in_trace": inspect_delivery.get("raw_private_text_in_trace"),
                },
                "durable_behavior_rows": {
                    "behavior_contracts": behavior_rows,
                    "compiled_behavior_policies": compiled_rows,
                },
            }
        finally:
            provider.shutdown()
    if out is not None:
        out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hermes-source",
        default=os.environ.get("BRAINSTACK_RELEASE_HERMES_SOURCE", str(DEFAULT_HERMES_SOURCE)),
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = run(hermes_source=Path(args.hermes_source), out=args.out)
    print(json.dumps({"status": report["status"], "issues": report["issues"]}, ensure_ascii=True, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
