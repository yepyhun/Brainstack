#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import importlib.util
import json
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORT_SCHEMA = "brainstack.enterprise_release_compliance.v1"


def _load_pyproject() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _dependency_name(spec: str) -> str:
    output = []
    for char in str(spec or "").strip():
        if char.isalnum() or char in {"_", "-", "."}:
            output.append(char)
            continue
        break
    return "".join(output).strip()


def _license_files() -> list[str]:
    candidates = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md")
    return [name for name in candidates if (ROOT / name).exists()]


def _dependency_specs(pyproject: dict[str, Any]) -> list[dict[str, str]]:
    project = pyproject.get("project") if isinstance(pyproject.get("project"), dict) else {}
    rows: list[dict[str, str]] = []
    for spec in project.get("dependencies") or ():
        name = _dependency_name(str(spec))
        if name:
            rows.append({"name": name, "spec": str(spec), "group": "default"})
    optional = project.get("optional-dependencies") if isinstance(project.get("optional-dependencies"), dict) else {}
    for group, specs in sorted(optional.items()):
        for spec in specs or ():
            name = _dependency_name(str(spec))
            if name:
                rows.append({"name": name, "spec": str(spec), "group": str(group)})
    return rows


def _installed_metadata(name: str) -> dict[str, Any]:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {"installed": False, "version": "", "license": "unknown"}
    meta = dist.metadata
    license_text = str(meta.get("License") or "").strip()
    classifiers = [value for value in meta.get_all("Classifier") or [] if str(value).startswith("License ::")]
    if not license_text and classifiers:
        license_text = "; ".join(classifiers)
    return {
        "installed": True,
        "version": str(dist.version or ""),
        "license": license_text or "unknown",
    }


def _dependency_license_report(pyproject: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for spec in _dependency_specs(pyproject):
        installed = _installed_metadata(spec["name"])
        rows.append({**spec, **installed})
    unknown = [row for row in rows if str(row.get("license") or "") == "unknown"]
    return {
        "status": "present",
        "dependency_count": len(rows),
        "unknown_license_count": len(unknown),
        "dependencies": rows,
    }


def _sbom(pyproject: dict[str, Any], license_report: dict[str, Any]) -> dict[str, Any]:
    project = pyproject.get("project") if isinstance(pyproject.get("project"), dict) else {}
    components = []
    for row in license_report.get("dependencies") or ():
        licenses = [] if str(row.get("license") or "") == "unknown" else [{"license": {"name": row["license"]}}]
        components.append(
            {
                "type": "library",
                "name": row["name"],
                "version": row.get("version") or row.get("spec") or "",
                "scope": row["group"],
                "licenses": licenses,
                "purl": f"pkg:pypi/{str(row['name']).lower()}",
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "name": str(project.get("name") or "brainstack-hermes-plugin"),
                "version": str(project.get("version") or ""),
            }
        },
        "components": components,
    }


def _release_hygiene() -> dict[str, Any]:
    checker_path = ROOT / "scripts" / "check_release_hygiene.py"
    spec = importlib.util.spec_from_file_location("brainstack_release_hygiene_for_compliance", checker_path)
    if spec is None or spec.loader is None:
        return {"status": "fail", "reason": "release_hygiene_loader_missing"}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module._load_release_hygiene_checker()(ROOT)


def build_report() -> dict[str, Any]:
    pyproject = _load_pyproject()
    license_files = _license_files()
    license_report = _dependency_license_report(pyproject)
    sbom = _sbom(pyproject, license_report)
    hygiene = _release_hygiene()
    vulnerability_tool = shutil.which("pip-audit")
    license_state = {
        "status": "explicit" if license_files else "decision_required_no_top_level_license",
        "files": license_files,
    }
    vulnerability_scan = {
        "status": "tool_unavailable" if vulnerability_tool is None else "tool_available_not_run_by_local_gate",
        "tool": "pip-audit",
        "tool_path": vulnerability_tool or "",
        "strict_enterprise_claim_blocker": vulnerability_tool is None,
    }
    strict_enterprise_claim_allowed = (
        bool(license_files)
        and hygiene.get("status") == "pass"
        and int(license_report.get("unknown_license_count") or 0) == 0
        and vulnerability_tool is not None
    )
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if hygiene.get("status") == "pass" else "fail",
        "public_safe": True,
        "license_state": license_state,
        "dependency_license_report": license_report,
        "sbom": sbom,
        "secret_scan": {
            "status": hygiene.get("status"),
            "private_tracked_count": len(hygiene.get("private_tracked") or []),
            "private_staged_count": len(hygiene.get("private_staged") or []),
            "secret_like_tracked_count": len(hygiene.get("secret_like_tracked") or []),
        },
        "vulnerability_scan": vulnerability_scan,
        "release_claim_boundary": {
            "local_memory_kernel_release_allowed_by_this_check": hygiene.get("status") == "pass",
            "strict_enterprise_claim_allowed": strict_enterprise_claim_allowed,
            "strict_enterprise_blockers": [
                blocker
                for blocker, active in (
                    ("license_decision_required", not license_files),
                    ("unknown_dependency_licenses", int(license_report.get("unknown_license_count") or 0) != 0),
                    ("vulnerability_tool_unavailable", vulnerability_tool is None),
                )
                if active
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "strict_enterprise_claim_allowed": report["release_claim_boundary"][
                    "strict_enterprise_claim_allowed"
                ],
                "blockers": report["release_claim_boundary"]["strict_enterprise_blockers"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
