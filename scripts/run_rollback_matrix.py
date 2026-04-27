#!/usr/bin/env python3
"""Emit Phase 179.5 hot containment rollback matrix probes."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import (  # noqa: E402
    ProbeOwner,
    ProbeStatus,
    ProductProbeEnvelope,
    Repairability,
    Severity,
    build_capability_manifest,
    continuity_visibility,
    default_hot_containment_toggles,
    direct_renderer_negative_allowed,
    dump_json,
)


def build_matrix() -> dict[str, object]:
    toggles = default_hot_containment_toggles()
    manifest = build_capability_manifest(
        configured_capabilities=("filesystem.search_read", "terminal.execute", "web.browse"),
        executable_capabilities=("filesystem.search_read", "terminal.execute", "web.browse"),
        approval_required_capabilities=("terminal.execute",),
    )
    visibility = continuity_visibility(source_role="assistant", claim_type="assistant_self_claim", truth_eligible=True)
    renderer = direct_renderer_negative_allowed(resolved_memory_target=False, localized_template=True)

    probes = [
        ProductProbeEnvelope(
            probe_id="179.5.personality.neutral",
            phase="179.5",
            scenario_id="neutral_personality",
            status=ProbeStatus.PASS if toggles.production_personality == "neutral" else ProbeStatus.FAIL,
            owner=ProbeOwner.HERMES_PRESENTATION,
            repairability=Repairability.REPAIRABLE_AUTOMATIC,
            severity=Severity.P1,
            reason_code="NEUTRAL_PERSONALITY_DEFAULT",
            observed={"production_personality": toggles.production_personality},
            expected={"production_personality": "neutral"},
            recommended_playbook="STYLE_PRESENTATION_FAILURE",
        ),
        ProductProbeEnvelope(
            probe_id="179.5.capability.preserved",
            phase="179.5",
            scenario_id="capability_preservation",
            status=ProbeStatus.PASS if not manifest["capability_shrunk"] else ProbeStatus.FAIL,
            owner=ProbeOwner.HERMES_CAPABILITY_MANIFEST,
            repairability=Repairability.REPAIRABLE_AUTOMATIC,
            severity=Severity.P0,
            reason_code="CAPABILITY_PRESERVED",
            observed={"capability_shrunk": manifest["capability_shrunk"]},
            expected={"capability_shrunk": False},
            recommended_playbook="TOOL_STATE_FINAL_ANSWER_BLOCK",
        ),
        ProductProbeEnvelope(
            probe_id="179.5.renderer.negative-contained",
            phase="179.5",
            scenario_id="negative_renderer_contained",
            status=ProbeStatus.PASS if not renderer["allowed"] else ProbeStatus.FAIL,
            owner=ProbeOwner.HERMES_PRESENTATION,
            repairability=Repairability.REPAIRABLE_AUTOMATIC,
            severity=Severity.P1,
            reason_code="NEGATIVE_RENDERER_CONTAINED",
            observed=renderer,
            expected={"allowed": False},
            recommended_playbook="STYLE_PRESENTATION_FAILURE",
        ),
        ProductProbeEnvelope(
            probe_id="179.5.assistant-output.not-model-facing",
            phase="179.5",
            scenario_id="assistant_output_containment",
            status=ProbeStatus.PASS if not visibility["model_facing_default"] else ProbeStatus.FAIL,
            owner=ProbeOwner.BRAINSTACK_RETRIEVAL_ANSWERABILITY,
            repairability=Repairability.REPAIRABLE_AUTOMATIC,
            severity=Severity.P1,
            reason_code="ASSISTANT_OUTPUT_CONTAINED",
            observed=visibility,
            expected={"model_facing_default": False},
            recommended_playbook="ASSISTANT_OUTPUT_CONTAINMENT",
        ),
        ProductProbeEnvelope(
            probe_id="179.5.toolloader.full-fallback",
            phase="179.5",
            scenario_id="full_configured_fallback",
            status=ProbeStatus.PASS if toggles.full_configured_tool_fallback_when_toolloader_unproven else ProbeStatus.FAIL,
            owner=ProbeOwner.HERMES_TOOL_LOADER,
            repairability=Repairability.REPAIRABLE_AUTOMATIC,
            severity=Severity.P1,
            reason_code="FULL_CONFIGURED_FALLBACK_AVAILABLE",
            observed={
                "full_configured_tool_fallback_when_toolloader_unproven": toggles.full_configured_tool_fallback_when_toolloader_unproven
            },
            expected={"full_configured_tool_fallback_when_toolloader_unproven": True},
            recommended_playbook="TOOL_STATE_FINAL_ANSWER_BLOCK",
        ),
    ]
    return {
        "schema": "brainstack.phase1795.rollback_matrix.v1",
        "profiles": {
            "A": "last_known_good_or_closest_pre_optimization",
            "B": "current_state",
            "C": "current_plus_direct_renderer_disabled",
            "D": "current_plus_assistant_output_model_facing_continuity_disabled",
            "E": "current_plus_neutral_personality_config",
            "F": "current_plus_full_configured_tool_fallback",
            "G": "current_plus_all_containment_toggles",
        },
        "toggles": toggles.to_dict(),
        "capability_manifest": manifest,
        "probes": [probe.to_dict() for probe in probes],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    dump_json(Path(args.out), build_matrix())
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
