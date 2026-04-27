#!/usr/bin/env python3
"""Write Phase 180 firewall proof artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import (  # noqa: E402
    classify_assistant_claim,
    dump_json,
    model_facing_packet_firewall,
)


def write_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = {
        "assistant_self_claim": classify_assistant_claim("assistant_self_claim"),
        "assistant_user_claim": classify_assistant_claim("assistant_user_claim"),
        "assistant_tool_capability_claim": classify_assistant_claim("assistant_tool_capability_claim"),
        "assistant_style_claim": classify_assistant_claim("assistant_style_claim"),
        "assistant_answer_summary": classify_assistant_claim("assistant_answer_summary"),
        "assistant_tool_result_paraphrase": classify_assistant_claim(
            "assistant_tool_result_paraphrase",
            linked_tool_result_id="tool_result:example",
        ),
        "assistant_commitment": classify_assistant_claim("assistant_commitment"),
        "assistant_dialogue_coherence": classify_assistant_claim("assistant_dialogue_coherence"),
    }
    (out_dir / "180-ASSISTANT-CLAIM-TAXONOMY.md").write_text(
        "\n".join(
            [
                "# Phase 180 Assistant Claim Taxonomy",
                "",
                "- Assistant output is raw history by default, not durable truth.",
                "- Assistant self/user/tool/style claims are not truth eligible.",
                "- Assistant tool result paraphrase can be support only when linked to a tool result row.",
                "- Assistant commitment is not a write receipt.",
                "- Historical queries may quote assistant output as history, never as truth.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dump_json(
        out_dir / "180-PACKET-FIREWALL-SPEC.json",
        {
            "schema": "brainstack.phase180.packet_firewall_spec.v1",
            "taxonomy": taxonomy,
            "normal_policy": {
                "answer_evidence_requires_truth_eligible": True,
                "drop_corrected_false": True,
                "drop_inspect_only": True,
                "drop_assistant_self_user_tool_style_claims": True,
                "support_only_cannot_be_answer_evidence": True,
                "runtime_capability_authority": "hermes_capability_manifest",
            },
        },
    )
    trace = model_facing_packet_firewall(
        [
            {"evidence_id": "assistant:self", "source_role": "assistant", "claim_type": "assistant_self_claim"},
            {"evidence_id": "corrected:false", "corrected_status": "corrected_false"},
            {"evidence_id": "support:answer", "evidence_class": "support_only", "answer_evidence": True},
            {
                "evidence_id": "truth:user",
                "source_role": "user",
                "truth_eligible": True,
                "answer_evidence": True,
            },
        ]
    )
    dump_json(out_dir / "180-FIREWALL-TRACE.json", trace)
    (out_dir / "180-FAILURE-PLAYBOOK-UPDATE.yaml").write_text(
        "\n".join(
            [
                "ASSISTANT_OUTPUT_CONTAINMENT:",
                "  owner: brainstack_retrieval_answerability",
                "  minimal_tests:",
                "    - tests/test_model_facing_packet_firewall.py",
                "    - tests/test_assistant_claim_classification.py",
                "  forbidden_fixes:",
                "    - observed_phrase_blacklist",
                "    - language_keyword_router",
                "    - raw_transcript_deletion",
                "    - brainstack_output_governor",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    write_artifacts(Path(args.out_dir))
    print(f"WROTE {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
