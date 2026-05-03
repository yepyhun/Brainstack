from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_fresh_hermes_brainstack_install import evaluate_installed_target


def test_evaluate_installed_target_requires_m007_payload_and_tei_runtime(tmp_path: Path) -> None:
    target = tmp_path / "hermes"
    plugin_root = target / "plugins" / "memory" / "brainstack"
    plugin_files = [
        "adaptive_consolidation.py",
        "adaptive_evidence_broker.py",
        "adaptive_evidence_hotpath.py",
        "adaptive_route_plan.py",
        "current_truth_view.py",
        "control_plane.py",
        "core/packet_budget.py",
        "diagnostics.py",
        "persistent_bloat.py",
        "projection_conformance.py",
    ]
    manifest_files = []
    for rel in plugin_files:
        path = plugin_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# installed\n", encoding="utf-8")
        manifest_files.append({"target": str(path), "source": f"brainstack/{rel}", "sha256": "0" * 64})
    (target / ".brainstack-install-manifest.json").write_text(
        json.dumps(
            {
                "runtime_mode": "docker",
                "files": manifest_files,
                "helper_files": [{"target": str(target / "scripts" / "helper.py")}],
                "generated_files": [{"target": str(target / "docker-compose.bestie.yml")}],
                "secrets_included": False,
                "source_only_install": False,
            }
        ),
        encoding="utf-8",
    )
    (target / "docker-compose.bestie.yml").write_text(
        """
services:
  tei-jina:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
    command:
      - --model-id
      - jinaai/jina-embeddings-v5-text-small-retrieval
    network_mode: host
  hermes:
    environment:
      - BRAINSTACK_EMBEDDINGS_URL=http://127.0.0.1:7997/embed
      - BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL=http://127.0.0.1:7997
    depends_on:
      tei-jina:
        condition: service_healthy
""",
        encoding="utf-8",
    )
    (target / "Dockerfile").write_text("RUN pip install kuzu chromadb openai croniter\n", encoding="utf-8")

    report = evaluate_installed_target(target)

    assert report["status"] == "pass"
    assert report["payload_status"] == "pass"
    assert report["missing_plugin_files"] == []
    assert report["compose"]["status"] == "pass"
    assert report["dockerfile"]["status"] == "pass"


def test_evaluate_installed_target_fails_when_adaptive_payload_missing(tmp_path: Path) -> None:
    target = tmp_path / "hermes"
    target.mkdir()
    (target / ".brainstack-install-manifest.json").write_text(
        json.dumps({"runtime_mode": "docker", "files": [], "secrets_included": False}),
        encoding="utf-8",
    )
    (target / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (target / "Dockerfile").write_text("RUN pip install kuzu chromadb openai croniter\n", encoding="utf-8")

    report = evaluate_installed_target(target)

    assert report["status"] == "fail"
    assert report["payload_status"] == "fail"
    assert "plugins/memory/brainstack/adaptive_route_plan.py" in report["missing_plugin_files"]
