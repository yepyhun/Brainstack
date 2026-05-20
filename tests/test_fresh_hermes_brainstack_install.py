from __future__ import annotations

import json
from pathlib import Path

from scripts import hermes_gateway_patch_support
from scripts.verify_fresh_hermes_brainstack_install import evaluate_installed_target, _required_plugin_files


def test_evaluate_installed_target_requires_m007_payload_and_tei_runtime(tmp_path: Path) -> None:
    target = tmp_path / "hermes"
    plugin_root = target / "plugins" / "memory" / "brainstack"
    plugin_files = [
        rel.removeprefix("plugins/memory/brainstack/")
        for rel in sorted(_required_plugin_files())
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
      - TERMINAL_CWD=/workspace
      - PATH=/opt/hermes/.venv/bin:/opt/data/bin:/usr/local/bin:/usr/bin
    volumes:
      - ./runtime/workspace:/workspace
    depends_on:
      tei-jina:
        condition: service_healthy
""",
        encoding="utf-8",
    )
    (target / "Dockerfile").write_text(
        """
RUN pip install kuzu chromadb openai croniter
RUN printf '%s\\n' '#!/bin/sh' 'exec /opt/hermes/.venv/bin/python "$@"' > /usr/local/bin/python && chmod 0755 /usr/local/bin/python
RUN printf '%s\\n' '#!/bin/sh' 'exec /opt/hermes/.venv/bin/hermes "$@"' > /usr/local/bin/hermes && chmod 0755 /usr/local/bin/hermes
""",
        encoding="utf-8",
    )
    start_script = target / "scripts" / "hermes-brainstack-start.sh"
    start_script.parent.mkdir(parents=True, exist_ok=True)
    start_script.write_text(
        """
SERVICE="${HERMES_DOCKER_SERVICE:-}"
EXPECTED_SERVICE="hermes-bestie"
if [ -z "$SERVICE" ] && [ -f "$COMPOSE_FILE" ]; then
  if awk -v svc="$EXPECTED_SERVICE" '$0 ~ "^[[:space:]]{2}" svc ":$" { found=1 } END { exit found ? 0 : 1 }' "$COMPOSE_FILE"; then
    SERVICE="$EXPECTED_SERVICE"
  else
    SERVICE=$(awk '
      /^[[:space:]]{2}[A-Za-z0-9_.-]+:$/ { svc=$1; gsub(":","",svc); next }
      /^[[:space:]]{4}container_name:[[:space:]]*hermes-.*-live[[:space:]]*$/ && svc { print svc; exit }
    ' "$COMPOSE_FILE")
  fi
fi
""",
        encoding="utf-8",
    )
    for relative, markers in hermes_gateway_patch_support.REQUIRED_GATEWAY_PROBES.items():
        probe_file = target / relative
        probe_file.parent.mkdir(parents=True, exist_ok=True)
        probe_file.write_text("\n".join(markers), encoding="utf-8")

    report = evaluate_installed_target(target)

    assert report["status"] == "pass"
    assert report["payload_status"] == "pass"
    assert report["missing_plugin_files"] == []
    assert report["compose"]["status"] == "pass"
    assert report["dockerfile"]["status"] == "pass"
    assert report["dockerfile"]["workstation_python_alias"] == "venv_wrapper"
    assert report["dockerfile"]["workstation_hermes_cli"] == "venv_wrapper"
    assert report["start_script"]["status"] == "pass"
    assert report["gateway_patch_status"] == "pass"


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
    assert report["gateway_patch_status"] == "fail"
    assert "plugins/memory/brainstack/adaptive_route_plan.py" in report["missing_plugin_files"]
    assert "plugins/memory/brainstack/operating_loop.py" in report["missing_plugin_files"]


def test_evaluate_installed_target_warns_on_gateway_auto_incompatible(
    tmp_path: Path,
) -> None:
    target = tmp_path / "hermes"
    plugin_root = target / "plugins" / "memory" / "brainstack"
    manifest_files = []
    for rel in sorted(_required_plugin_files()):
        plugin_rel = rel.removeprefix("plugins/memory/brainstack/")
        path = plugin_root / plugin_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# installed\n", encoding="utf-8")
        manifest_files.append({"target": str(path), "source": f"brainstack/{plugin_rel}", "sha256": "0" * 64})
    (target / ".brainstack-install-manifest.json").write_text(
        json.dumps(
            {
                "runtime_mode": "docker",
                "files": manifest_files,
                "helper_files": [{"target": str(target / "scripts" / "helper.py")}],
                "generated_files": [{"target": str(target / "docker-compose.bestie.yml")}],
                "secrets_included": False,
                "source_only_install": False,
                "hermes_gateway_patches": {
                    "mode": "auto",
                    "status": "gateway_patch_incompatible",
                    "error": "patch does not apply",
                },
            }
        ),
        encoding="utf-8",
    )
    (target / "docker-compose.bestie.yml").write_text(
        """
services:
  tei-jina:
    image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.9
    command: [--model-id, jinaai/jina-embeddings-v5-text-small-retrieval]
    network_mode: host
  hermes:
    environment:
      - BRAINSTACK_EMBEDDINGS_URL=http://127.0.0.1:7997/embed
      - BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL=http://127.0.0.1:7997
      - TERMINAL_CWD=/workspace
      - PATH=/opt/hermes/.venv/bin:/opt/data/bin:/usr/local/bin:/usr/bin
    volumes:
      - ./runtime/workspace:/workspace
    depends_on:
      tei-jina:
        condition: service_healthy
""",
        encoding="utf-8",
    )
    (target / "Dockerfile").write_text(
        "RUN pip install kuzu chromadb openai croniter\n"
        "RUN printf '%s\\n' '#!/bin/sh' 'exec /opt/hermes/.venv/bin/python \"$@\"' > /usr/local/bin/python && chmod 0755 /usr/local/bin/python\n"
        "RUN printf '%s\\n' '#!/bin/sh' 'exec /opt/hermes/.venv/bin/hermes \"$@\"' > /usr/local/bin/hermes && chmod 0755 /usr/local/bin/hermes\n",
        encoding="utf-8",
    )
    start_script = target / "scripts" / "hermes-brainstack-start.sh"
    start_script.parent.mkdir(parents=True, exist_ok=True)
    start_script.write_text(
        """
SERVICE="${HERMES_DOCKER_SERVICE:-}"
EXPECTED_SERVICE="hermes-bestie"
if [ -z "$SERVICE" ] && [ -f "$COMPOSE_FILE" ]; then
  if awk -v svc="$EXPECTED_SERVICE" '$0 ~ "^[[:space:]]{2}" svc ":$" { found=1 } END { exit found ? 0 : 1 }' "$COMPOSE_FILE"; then
    SERVICE="$EXPECTED_SERVICE"
  else
    SERVICE=$(awk '
      /^[[:space:]]{2}[A-Za-z0-9_.-]+:$/ { svc=$1; gsub(":", "", svc); next }
      /^[[:space:]]{4}container_name:[[:space:]]*hermes-.*-live[[:space:]]*$/ && svc { print svc; exit }
    ' "$COMPOSE_FILE")
  fi
fi
""",
        encoding="utf-8",
    )

    report = evaluate_installed_target(target)

    assert report["status"] == "pass"
    assert report["gateway_patch_status"] == "warn"
    assert report["gateway_patch"]["manifest_status"] == "gateway_patch_incompatible"


def test_evaluate_installed_target_fails_legacy_python_alias_and_naive_service_picker(tmp_path: Path) -> None:
    target = tmp_path / "hermes"
    target.mkdir()
    (target / ".brainstack-install-manifest.json").write_text(
        json.dumps({"runtime_mode": "docker", "files": [], "secrets_included": False}),
        encoding="utf-8",
    )
    (target / "docker-compose.bestie.yml").write_text(
        """
services:
  tei-jina:
    image: tei
  hermes-bestie:
    container_name: hermes-bestie-live
    environment:
      TERMINAL_CWD: /workspace
      PATH: /opt/hermes/.venv/bin:/opt/data/bin:/usr/local/bin:/usr/bin
    volumes:
      - ./runtime/workspace:/workspace
""",
        encoding="utf-8",
    )
    (target / "Dockerfile").write_text(
        "RUN pip install kuzu chromadb openai croniter\nRUN ln -sf /usr/bin/python3 /usr/local/bin/python\n",
        encoding="utf-8",
    )
    start_script = target / "scripts" / "hermes-brainstack-start.sh"
    start_script.parent.mkdir(parents=True, exist_ok=True)
    start_script.write_text(
        "SERVICE=$(awk '/^[[:space:]]{2}[A-Za-z0-9_.-]+:$/ {gsub(\":\",\"\",$1); print $1; exit}' \"$COMPOSE_FILE\")\n",
        encoding="utf-8",
    )

    report = evaluate_installed_target(target)

    assert report["status"] == "fail"
    assert report["dockerfile"]["workstation_python_alias"] == "legacy_system_python"
    assert report["dockerfile"]["workstation_hermes_cli"] == "missing"
    assert report["start_script"]["status"] == "fail"
    assert report["start_script"]["first_service_naive"] is True
