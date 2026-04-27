#!/usr/bin/env python3
"""Write Phase 183 reference URL and URL guard artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.product_contracts import admit_reference_url, decide_url_content_claim_allowed, dump_json  # noqa: E402


def write_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "183-REFERENCE-SCHEMA.md").write_text(
        "\n".join(
            [
                "# Phase 183 Reference Schema",
                "",
                "- `reference.repository_url`: named repository reference from explicit user memory write.",
                "- `reference.url`: generic named URL reference.",
                "- `project.related_repo`: related repo when project scope is resolved.",
                "- `project.repo_url`: owning project repository only, not arbitrary related URL.",
                "- `fetch_on_write=false`: remembering is not opening.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    record = admit_reference_url(
        label="resource-x",
        url="https://example.com/org/resource-x",
        source_authority="user_explicit_assertion",
    )
    dump_json(
        out_dir / "183-REFERENCE-ADMISSION-MATRIX.json",
        {
            "schema": "brainstack.phase183.reference_admission_matrix.v1",
            "explicit_reference": record,
            "resolved_related_repo": admit_reference_url(
                label="resource-x",
                url="https://example.com/org/resource-x",
                source_authority="user_explicit_assertion",
                resolved_project_scope="project:alpha",
            ),
            "unresolved_project_repo": admit_reference_url(
                label="resource-x",
                url="https://example.com/org/resource-x",
                source_authority="user_explicit_assertion",
                as_project_repo_url=True,
            ),
        },
    )
    dump_json(
        out_dir / "183-URL-GUARD-TRACE.json",
        {
            "schema": "brainstack.phase183.url_guard_trace.v1",
            "remember_only": decide_url_content_claim_allowed(
                url_present=True,
                content_claim_made=False,
                remember_only=True,
            ),
            "unavailable": decide_url_content_claim_allowed(
                url_present=True,
                content_claim_made=True,
                unavailable_diagnostic_emitted=True,
            ),
            "blocked_guess": decide_url_content_claim_allowed(
                url_present=True,
                content_claim_made=True,
            ),
            "with_tool_result": decide_url_content_claim_allowed(
                url_present=True,
                content_claim_made=True,
                web_tool_result_id="web:result:1",
            ),
        },
    )
    (out_dir / "183-FAILURE-PLAYBOOK-UPDATE.yaml").write_text(
        "\n".join(
            [
                "URL_CONTENT_GUARD:",
                "  owner: hermes_tool_state_guard",
                "  minimal_tests:",
                "    - tests/test_url_fetch_guard.py",
                "    - tests/test_reference_url_admission.py",
                "  forbidden_fixes:",
                "    - language_keyword_router",
                "    - hardcoded_reference_url",
                "    - auto_fetch_on_write",
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
