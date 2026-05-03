#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "brainstack.fresh_hermes_brainstack_install_proof.v1"

REQUIRED_PLUGIN_FILES = {
    "plugins/memory/brainstack/adaptive_consolidation.py",
    "plugins/memory/brainstack/adaptive_evidence_broker.py",
    "plugins/memory/brainstack/adaptive_evidence_hotpath.py",
    "plugins/memory/brainstack/adaptive_route_plan.py",
    "plugins/memory/brainstack/current_truth_view.py",
    "plugins/memory/brainstack/control_plane.py",
    "plugins/memory/brainstack/core/packet_budget.py",
    "plugins/memory/brainstack/diagnostics.py",
    "plugins/memory/brainstack/persistent_bloat.py",
    "plugins/memory/brainstack/projection_conformance.py",
}

REQUIRED_DOCKERFILE_DEPENDENCIES = {"kuzu", "chromadb", "openai", "croniter"}


def _run(command: list[str], *, cwd: Path | None = None, timeout: int = 300) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    return {
        "command": [Path(command[0]).name, *command[1:]],
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def _clone_source(source: Path, target: Path) -> dict[str, Any]:
    return _run(["git", "clone", "--local", "--no-hardlinks", str(source), str(target)], timeout=120)


def _write_minimal_agent_config(target: Path, agent_name: str) -> Path:
    config = target / "hermes-config" / agent_name / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    if not config.exists():
        config.write_text("memory: {}\nplugins: {}\n", encoding="utf-8")
    return config


def _load_manifest(target: Path) -> dict[str, Any]:
    path = target / ".brainstack-install-manifest.json"
    if not path.exists():
        return {"status": "missing", "path": path.name}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "invalid_json", "path": path.name, "error": str(exc)}
    if not isinstance(payload, dict):
        return {"status": "invalid_shape", "path": path.name}
    payload["status"] = "present"
    return payload


def _relative_installed_files(target: Path, manifest: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for item in manifest.get("files") or []:
        if not isinstance(item, dict):
            continue
        raw_target = item.get("target")
        if not isinstance(raw_target, str):
            continue
        try:
            files.add(Path(raw_target).resolve().relative_to(target.resolve()).as_posix())
        except ValueError:
            continue
    return files


def _compose_candidates(target: Path) -> list[Path]:
    return sorted(path for path in target.glob("docker-compose*.yml") if path.is_file())


def _compose_checks(target: Path) -> dict[str, Any]:
    candidates = _compose_candidates(target)
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in candidates)
    checks = {
        "compose_file_count": len(candidates),
        "tei_jina_service": "tei-jina:" in text,
        "jina_v5_model": "jinaai/jina-embeddings-v5-text-small-retrieval" in text,
        "tei_embed_url": "BRAINSTACK_EMBEDDINGS_URL" in text and "http://127.0.0.1:7997/embed" in text,
        "tier2_tei_url": "BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL" in text
        and "http://127.0.0.1:7997" in text,
        "host_network": "network_mode: host" in text,
        "service_health_dependency": "condition: service_healthy" in text,
    }
    checks["status"] = "pass" if all(value is True for key, value in checks.items() if key != "compose_file_count") and candidates else "fail"
    return checks


def _dockerfile_checks(target: Path) -> dict[str, Any]:
    dockerfile = target / "Dockerfile"
    if not dockerfile.exists():
        return {"status": "fail", "missing": sorted(REQUIRED_DOCKERFILE_DEPENDENCIES), "dockerfile_present": False}
    text = dockerfile.read_text(encoding="utf-8", errors="replace")
    missing = sorted(dep for dep in REQUIRED_DOCKERFILE_DEPENDENCIES if dep not in text)
    return {
        "status": "pass" if not missing else "fail",
        "dockerfile_present": True,
        "missing": missing,
    }


def evaluate_installed_target(target: Path) -> dict[str, Any]:
    manifest = _load_manifest(target)
    installed_files = _relative_installed_files(target, manifest) if manifest.get("status") == "present" else set()
    missing_plugin_files = sorted(REQUIRED_PLUGIN_FILES - installed_files)
    compose = _compose_checks(target)
    dockerfile = _dockerfile_checks(target)
    manifest_status = "pass" if manifest.get("status") == "present" and manifest.get("secrets_included") is False else "fail"
    payload_status = "pass" if not missing_plugin_files else "fail"
    status = "pass" if all(
        item == "pass"
        for item in (manifest_status, payload_status, compose.get("status"), dockerfile.get("status"))
    ) else "fail"
    return {
        "schema": "brainstack.fresh_hermes_brainstack_install_evaluation.v1",
        "status": status,
        "manifest": {
            "status": manifest.get("status"),
            "runtime_mode": manifest.get("runtime_mode"),
            "payload_file_count": len(manifest.get("files") or []),
            "helper_file_count": len(manifest.get("helper_files") or []),
            "generated_file_count": len(manifest.get("generated_files") or []),
            "secrets_included": manifest.get("secrets_included"),
            "source_only_install": manifest.get("source_only_install"),
        },
        "manifest_status": manifest_status,
        "payload_status": payload_status,
        "missing_plugin_files": missing_plugin_files,
        "compose": compose,
        "dockerfile": dockerfile,
    }


def _build_runtime_proof(target: Path, *, timeout: int) -> dict[str, Any]:
    compose_files = _compose_candidates(target)
    if not compose_files:
        return {"status": "skipped", "reason": "compose_file_missing"}
    compose_file = compose_files[0]
    build = _run(["docker", "compose", "-f", str(compose_file), "build"], cwd=target, timeout=timeout)
    return {
        "status": "pass" if build["returncode"] == 0 else "fail",
        "compose_file": compose_file.name,
        "build": build,
    }


def build_report(
    *,
    source_hermes: Path,
    keep_temp: bool = False,
    docker_build: bool = False,
    docker_build_timeout: int = 1200,
) -> dict[str, Any]:
    temp_dir_obj: tempfile.TemporaryDirectory[str] | None = None
    if keep_temp:
        target = Path(tempfile.mkdtemp(prefix="brainstack-fresh-hermes-install-"))
    else:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="brainstack-fresh-hermes-install-")
        target = Path(temp_dir_obj.name)

    clone = _clone_source(source_hermes, target)
    install: dict[str, Any] = {"status": "not_run"}
    evaluation: dict[str, Any] = {"status": "not_run"}
    runtime: dict[str, Any] = {"status": "skipped", "reason": "not_requested"}
    try:
        if clone["returncode"] == 0:
            config = _write_minimal_agent_config(target, "brainstack-proof")
            installer = ROOT / "scripts" / "install_into_hermes.py"
            install_command = [
                sys.executable,
                str(installer),
                str(target),
                "--enable",
                "--config",
                str(config),
                "--skip-deps",
            ]
            install = _run(install_command, timeout=300)
            evaluation = evaluate_installed_target(target)
            if docker_build and evaluation.get("status") == "pass":
                runtime = _build_runtime_proof(target, timeout=docker_build_timeout)
    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()

    failure_reasons: list[str] = []
    if clone["returncode"] != 0:
        failure_reasons.append("fresh_clone_failed")
    if install.get("returncode") != 0:
        failure_reasons.append("installer_failed")
    if evaluation.get("status") != "pass":
        failure_reasons.append("install_evaluation_failed")
    if docker_build and runtime.get("status") != "pass":
        failure_reasons.append("docker_build_failed")

    return {
        "schema": SCHEMA,
        "status": "pass" if not failure_reasons else "fail",
        "failure_reasons": failure_reasons,
        "source": {"kind": "local_hermes_clone", "name": source_hermes.name},
        "temp_target": {"kept": keep_temp, "name": target.name if keep_temp else "removed"},
        "clone": clone,
        "install": install,
        "evaluation": evaluation,
        "runtime_proof": runtime,
        "public_safe": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify fresh Hermes clone Brainstack installer parity.")
    parser.add_argument("--source-hermes", type=Path, required=True, help="Local Hermes source checkout to clone from.")
    parser.add_argument("--out", type=Path, required=True, help="Public-safe JSON report path.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary Hermes clone for manual inspection.")
    parser.add_argument("--docker-build", action="store_true", help="Also run docker compose build in the fresh clone.")
    parser.add_argument("--docker-build-timeout", type=int, default=1200)
    args = parser.parse_args()

    report = build_report(
        source_hermes=args.source_hermes.expanduser().resolve(),
        keep_temp=args.keep_temp,
        docker_build=args.docker_build,
        docker_build_timeout=args.docker_build_timeout,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "failure_reasons": report["failure_reasons"],
        "install_status": report["evaluation"].get("status"),
        "runtime_proof_status": report["runtime_proof"].get("status"),
    }, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
