#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.hermes_gateway_patch_support import inspect_gateway_patch_support  # noqa: E402

SCHEMA = "brainstack.fresh_hermes_brainstack_install_proof.v1"

REQUIRED_DOCKERFILE_DEPENDENCIES = {"kuzu", "chromadb", "openai", "croniter"}


def _required_plugin_files() -> set[str]:
    """Return every public Brainstack plugin payload file expected in Hermes.

    The installer copies the full `brainstack/` package into
    `plugins/memory/brainstack/`. A static sample list lets new modules pass
    fresh-install verification while missing from the live plugin payload; this
    function makes the verifier check source-of-truth completeness instead.
    """

    source_root = ROOT / "brainstack"
    required: set[str] = set()
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.name.endswith(".pyc"):
            continue
        rel = path.relative_to(source_root).as_posix()
        required.add(f"plugins/memory/brainstack/{rel}")
    return required


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=env,
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
    terminal_cwd_workspace = "TERMINAL_CWD: /workspace" in text or "- TERMINAL_CWD=/workspace" in text
    workspace_mount = ":/workspace" in text or "target: /workspace" in text
    path_has_hermes_venv = "/opt/hermes/.venv/bin" in text
    path_has_data_bin = "/opt/data/bin" in text
    checks = {
        "compose_file_count": len(candidates),
        "tei_jina_service": "tei-jina:" in text,
        "jina_v5_model": "jinaai/jina-embeddings-v5-text-small-retrieval" in text,
        "tei_embed_url": "BRAINSTACK_EMBEDDINGS_URL" in text and "http://127.0.0.1:7997/embed" in text,
        "tier2_tei_url": "BRAINSTACK_TIER2_HINDSIGHT_EMBEDDINGS_TEI_URL" in text
        and "http://127.0.0.1:7997" in text,
        "host_network": "network_mode: host" in text,
        "service_health_dependency": "condition: service_healthy" in text,
        "terminal_cwd_workspace": terminal_cwd_workspace,
        "workspace_mount": workspace_mount,
        "terminal_path_has_hermes_venv": path_has_hermes_venv,
        "terminal_path_has_data_bin": path_has_data_bin,
        "workstation_contract": {
            "status": "pass"
            if terminal_cwd_workspace and workspace_mount and path_has_hermes_venv and path_has_data_bin
            else "fail",
            "cwd": "/workspace exists" if workspace_mount else "/workspace missing",
            "python_authority": "hermes_venv" if path_has_hermes_venv else "broken",
            "hermes_cli": "on_path" if path_has_hermes_venv else "missing",
            "imports": "probe_required_at_runtime",
        },
    }
    checks["status"] = (
        "pass"
        if all(
            value is True
            for key, value in checks.items()
            if key not in {"compose_file_count", "workstation_contract"}
        )
        and checks["workstation_contract"]["status"] == "pass"
        and candidates
        else "fail"
    )
    return checks


def _dockerfile_checks(target: Path) -> dict[str, Any]:
    dockerfile = target / "Dockerfile"
    if not dockerfile.exists():
        return {
            "status": "fail",
            "missing": sorted(REQUIRED_DOCKERFILE_DEPENDENCIES),
            "dockerfile_present": False,
            "workstation_python_alias": "missing",
            "workstation_hermes_cli": "missing",
        }
    text = dockerfile.read_text(encoding="utf-8", errors="replace")
    missing = sorted(dep for dep in REQUIRED_DOCKERFILE_DEPENDENCIES if dep not in text)
    workstation_python_alias = (
        "venv_wrapper"
        if 'exec /opt/hermes/.venv/bin/python "$@"' in text
        else "legacy_system_python"
        if "ln -sf /usr/bin/python3 /usr/local/bin/python" in text
        else "missing"
    )
    workstation_hermes_cli = (
        "venv_wrapper" if 'exec /opt/hermes/.venv/bin/hermes "$@"' in text else "missing"
    )
    return {
        "status": "pass"
        if not missing
        and workstation_python_alias == "venv_wrapper"
        and workstation_hermes_cli == "venv_wrapper"
        else "fail",
        "dockerfile_present": True,
        "missing": missing,
        "workstation_python_alias": workstation_python_alias,
        "workstation_hermes_cli": workstation_hermes_cli,
    }


def _start_script_checks(target: Path) -> dict[str, Any]:
    scripts = sorted((target / "scripts").glob("hermes-brainstack-start.sh"))
    if not scripts:
        return {"status": "fail", "script_present": False, "reason": "missing_start_script"}
    text = scripts[0].read_text(encoding="utf-8", errors="replace")
    expected_service = 'EXPECTED_SERVICE="hermes-' in text
    expected_service_selected = 'SERVICE="$EXPECTED_SERVICE"' in text
    fallback_container_lookup = "container_name:[[:space:]]*hermes-.*-live" in text
    first_service_naive = "print $1; exit" in text
    passed = expected_service and expected_service_selected and fallback_container_lookup and not first_service_naive
    return {
        "status": "pass" if passed else "fail",
        "script_present": True,
        "expected_service": expected_service,
        "expected_service_selected": expected_service_selected,
        "fallback_container_lookup": fallback_container_lookup,
        "first_service_naive": first_service_naive,
    }


def evaluate_installed_target(target: Path) -> dict[str, Any]:
    manifest = _load_manifest(target)
    installed_files = _relative_installed_files(target, manifest) if manifest.get("status") == "present" else set()
    required_plugin_files = _required_plugin_files()
    missing_plugin_files = sorted(required_plugin_files - installed_files)
    compose = _compose_checks(target)
    dockerfile = _dockerfile_checks(target)
    start_script = _start_script_checks(target)
    gateway_patch = inspect_gateway_patch_support(target)
    manifest_gateway_patch = manifest.get("hermes_gateway_patches") or {}
    manifest_status = "pass" if manifest.get("status") == "present" and manifest.get("secrets_included") is False else "fail"
    payload_status = "pass" if not missing_plugin_files else "fail"
    gateway_patch_status = "pass" if gateway_patch.get("status") == "upstream_gateway_supported" else "fail"
    if (
        gateway_patch_status == "fail"
        and manifest_gateway_patch.get("mode") == "auto"
        and manifest_gateway_patch.get("status") == "gateway_patch_incompatible"
    ):
        gateway_patch_status = "warn"
    status = "pass" if all(
        item in {"pass", "warn"}
        for item in (
            manifest_status,
            payload_status,
            compose.get("status"),
            dockerfile.get("status"),
            start_script.get("status"),
            gateway_patch_status,
        )
    ) else "fail"
    return {
        "schema": "brainstack.fresh_hermes_brainstack_install_evaluation.v1",
        "status": status,
        "manifest": {
            "status": manifest.get("status"),
            "runtime_mode": manifest.get("runtime_mode"),
            "payload_file_count": len(manifest.get("files") or []),
            "required_plugin_file_count": len(required_plugin_files),
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
        "start_script": start_script,
        "gateway_patch_status": gateway_patch_status,
        "gateway_patch": {
            "status": gateway_patch.get("status"),
            "missing_files": gateway_patch.get("missing_files"),
            "manifest_status": manifest_gateway_patch.get("status"),
            "manifest_mode": manifest_gateway_patch.get("mode"),
            "manifest_error": manifest_gateway_patch.get("error"),
        },
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
            install_env = dict(os.environ)
            existing_pythonpath = install_env.get("PYTHONPATH")
            install_env["PYTHONPATH"] = (
                str(ROOT) if not existing_pythonpath else f"{ROOT}{os.pathsep}{existing_pythonpath}"
            )
            install = _run(install_command, timeout=300, env=install_env)
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
