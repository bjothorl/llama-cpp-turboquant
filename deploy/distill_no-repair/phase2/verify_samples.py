#!/usr/bin/env python3
"""Verify Phase 1 JSONL samples without mutating the raw corpus."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = Path(__file__).resolve().parent / "verifier.env"


@dataclass
class CheckResult:
    name: str
    ok: bool
    command: list[str] | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    skipped: bool = False
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "skipped": self.skipped,
            "reason": self.reason,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--node-sandbox", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--keep-workdir", action="store_true", default=None)
    parser.add_argument("--install-node-deps", action="store_true", default=None, help="Run npm install in Node/TypeScript workdirs before checks")
    parser.add_argument("--ids-file", default=None, help="Optional newline-delimited sample IDs to verify")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many samples after filtering")
    parser.add_argument("--max-samples", type=int, default=None, help="Verify at most this many samples after filtering")
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise SystemExit(f"{path}:{line_no}: expected KEY=VALUE")
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def env_value(args: argparse.Namespace, attr: str, env_name: str, default: str) -> str:
    value = getattr(args, attr)
    if value is not None:
        return str(value)
    return os.environ.get(env_name, default)


def env_bool(args: argparse.Namespace, attr: str, env_name: str, default: bool) -> bool:
    value = getattr(args, attr)
    if value is not None:
        return bool(value)
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def load_ids(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    return {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def run_command(command: list[str], cwd: Path, timeout: float, name: str) -> CheckResult:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return CheckResult(name=name, ok=False, command=command, skipped=True, reason=str(exc))
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            name=name,
            ok=False,
            command=command,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            reason=f"timed out after {timeout}s",
        )
    return CheckResult(
        name=name,
        ok=result.returncode == 0,
        command=command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def run_optional_node_command(command: list[str], cwd: Path, timeout: float, name: str) -> CheckResult:
    result = run_command(command, cwd, timeout, name)
    combined = f"{result.stdout}\n{result.stderr}".lower()
    missing_package_markers = [
        "npx canceled due to missing packages",
        "could not determine executable to run",
        "not found",
        "cannot find package",
    ]
    if result.returncode != 0 and any(marker in combined for marker in missing_package_markers):
        return CheckResult(
            name=name,
            ok=False,
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            skipped=True,
            reason="node tool/dependency unavailable without install",
        )
    return result


def normalize_python_tests(test_code: str) -> str:
    normalized = test_code.replace("from .solution import", "from solution import")
    preserved_modules = {"collections", "datetime", "decimal", "functools", "itertools", "json", "math", "os", "pathlib", "pytest", "re", "sys", "typing", "unittest"}

    def replace_from_import(match: re.Match[str]) -> str:
        module = match.group(1)
        imported = match.group(2)
        if module in preserved_modules or "." in module:
            return match.group(0)
        return f"from solution import {imported}"

    def replace_import(match: re.Match[str]) -> str:
        module = match.group(1)
        if module in preserved_modules:
            return match.group(0)
        return f"import solution as {module}"

    normalized = re.sub(r"^from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import\s+(.+)$", replace_from_import, normalized, flags=re.MULTILINE)
    normalized = re.sub(r"^import\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", replace_import, normalized, flags=re.MULTILINE)
    if "unittest." in normalized and "import unittest" not in normalized:
        normalized = "import unittest\n" + normalized
    if "import solution" not in normalized and "from solution import" not in normalized:
        normalized = "from solution import *\n\n" + normalized
    return normalized


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def verify_python(sample: dict[str, Any], sample_dir: Path, timeout: float) -> list[CheckResult]:
    (sample_dir / "solution.py").write_text(sample["code"].rstrip() + "\n")
    (sample_dir / "test_solution.py").write_text(normalize_python_tests(sample["tests"]).rstrip() + "\n")
    checks = [
        run_command([sys.executable, "-m", "py_compile", "solution.py"], sample_dir, timeout, "python:compile-solution"),
        run_command([sys.executable, "-m", "py_compile", "test_solution.py"], sample_dir, timeout, "python:compile-tests"),
    ]
    if shutil.which("pytest"):
        checks.append(run_command([sys.executable, "-m", "pytest", "-q", "test_solution.py"], sample_dir, timeout, "python:pytest"))
    else:
        checks.append(run_command([sys.executable, "-m", "unittest", "discover", "-v"], sample_dir, timeout, "python:unittest"))
    return checks


def ts_extension(language: str) -> str:
    if language.lower() == "javascript":
        return "js"
    return "ts"


def package_json_for(sample: dict[str, Any]) -> dict[str, Any]:
    language = sample.get("language", "")
    is_ts = language in {"typescript", "ts"}
    is_react = "react" in sample.get("code", "").lower() or "@testing-library/react" in sample.get("tests", "")
    test_code = sample.get("tests", "")
    has_test_globals = any(marker in test_code for marker in ("describe(", "it(", "test(", "expect("))
    dev_deps: dict[str, str] = {}
    scripts: dict[str, str] = {}
    if is_ts:
        scripts["typecheck"] = "tsc --noEmit --pretty false"
        dev_deps["typescript"] = "*"
    if "node:test" in test_code and not is_ts:
        scripts["test"] = "node --test"
    elif is_react or "vitest" in test_code or has_test_globals:
        scripts["test"] = "vitest run"
        dev_deps["vitest"] = "*"
    elif "jest" in test_code:
        scripts["test"] = "jest --runInBand"
        dev_deps["jest"] = "*"
    if "@testing-library" in test_code:
        dev_deps["@types/jest"] = "*"
        dev_deps["@types/react"] = "*"
        dev_deps["@types/react-dom"] = "*"
        dev_deps["@testing-library/react"] = "*"
        dev_deps["@testing-library/jest-dom"] = "*"
        dev_deps["react"] = "*"
        dev_deps["react-dom"] = "*"
    if "express" in sample.get("code", "") or "express" in test_code:
        dev_deps["express"] = "*"
    if "supertest" in test_code:
        dev_deps["supertest"] = "*"
    if "zod" in sample.get("code", "") or "zod" in sample.get("tests", ""):
        dev_deps["zod"] = "*"
    return {
        "private": True,
        "type": "module" if is_ts else "commonjs",
        "scripts": scripts,
        "devDependencies": dev_deps,
    }


def node_sandbox_package_json() -> dict[str, Any]:
    return {
        "private": True,
        "type": "module",
        "devDependencies": {
            "@testing-library/jest-dom": "*",
            "@testing-library/react": "*",
            "@types/jest": "*",
            "@types/node": "*",
            "@types/react": "*",
            "@types/react-dom": "*",
            "jest": "*",
            "express": "*",
            "jsdom": "*",
            "react": "*",
            "react-dom": "*",
            "supertest": "*",
            "typescript": "*",
            "vite": "*",
            "vitest": "*",
            "zod": "*",
        },
    }


FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)\n(?P<body>.*?)```", re.DOTALL)
OPENING_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+.-]*\s*$")


def strip_markdown_fences(code: str) -> str:
    """Remove markdown code fences the test extractor sometimes leaves behind."""
    stripped = code.strip()
    if not stripped.startswith("```"):
        return code

    matches = list(FENCE_RE.finditer(stripped))
    if matches:
        candidates = [match.group("body").strip() for match in matches if match.group("body").strip()]
        if candidates:
            for body in candidates:
                if re.search(r"\b(describe|it|test|expect)\s*\(", body):
                    return body
            return candidates[0]

    lines = stripped.splitlines()
    while lines and OPENING_FENCE_RE.match(lines[0].strip()):
        lines = lines[1:]
    while lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    if lines != stripped.splitlines():
        return "\n".join(lines).strip() + ("\n" if code.endswith("\n") else "")
    return code


def normalize_js_ts_tests(test_code: str, language: str) -> str:
    normalized = strip_markdown_fences(test_code)
    normalized = re.sub(r"from\s+['\"]\./[^'\"]+['\"]", "from './solution'", normalized)
    normalized = re.sub(r"require\(['\"]\./[^'\"]+['\"]\)", "require('./solution')", normalized)
    if language in {"typescript", "ts"}:
        normalized = normalized.replace("from 'node:test'", "from 'vitest'")
        normalized = normalized.replace('from "node:test"', 'from "vitest"')
    normalized = re.sub(r"import\s+\{\s*describe\s*,\s*it\s*\}\s+from\s+['\"]mocha['\"];", "import { describe, it, expect } from 'vitest';", normalized)
    normalized = re.sub(r"import\s+\{\s*expect\s*\}\s+from\s+['\"]chai['\"];\n?", "", normalized)
    normalized = normalized.replace(".to.deep.equal(", ".toEqual(")
    normalized = normalized.replace(".to.equal(", ".toBe(")
    if "jest." in normalized and "vitest" not in normalized:
        if language in {"typescript", "ts"}:
            normalized = "import { vi } from 'vitest';\n" + normalized
        normalized = normalized.replace("jest.", "vi.")
    return normalized


def write_tsconfig(sample_dir: Path, *, jest_dom: bool = False) -> None:
    types = ["node", "vitest"]
    if jest_dom:
        types.append("@testing-library/jest-dom")
    write_json(sample_dir / "tsconfig.json", {
        "compilerOptions": {
            "target": "ES2022",
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "jsx": "react-jsx",
            "strict": True,
            "esModuleInterop": True,
            "skipLibCheck": True,
            "types": types,
        },
        "include": ["*.ts", "*.tsx"],
    })


def uses_jest_dom_matchers(sample: dict[str, Any]) -> bool:
    tests = sample.get("tests", "")
    markers = (
        "toHaveClass",
        "toHaveAttribute",
        "toBeInTheDocument",
        "toBeDisabled",
        "toBeVisible",
        "toBeEmptyDOMElement",
        "@testing-library/jest-dom",
    )
    return any(marker in tests for marker in markers)


def write_vitest_setup(sample_dir: Path) -> None:
    (sample_dir / "vitest.setup.ts").write_text("import '@testing-library/jest-dom/vitest';\n")


def write_vitest_config(sample_dir: Path, is_react: bool, *, jest_dom: bool = False) -> None:
    config = [
        "import { defineConfig } from 'vitest/config';",
        "",
        "export default defineConfig({",
        "  test: {",
        "    globals: true,",
    ]
    if is_react:
        config.append("    environment: 'jsdom',")
    if jest_dom:
        config.append("    setupFiles: ['./vitest.setup.ts'],")
    config.extend([
        "  },",
        "});",
        "",
    ])
    (sample_dir / "vitest.config.mjs").write_text("\n".join(config))


def npm_install(sample_dir: Path, timeout: float) -> CheckResult:
    if not shutil.which("npm"):
        return CheckResult(name="node:npm-install", ok=False, skipped=True, reason="npm not found")
    return run_command(["npm", "install", "--no-audit", "--no-fund"], sample_dir, timeout, "node:npm-install")


def prepare_node_sandbox(node_sandbox: Path, timeout: float, install_node_deps: bool) -> CheckResult | None:
    node_sandbox.mkdir(parents=True, exist_ok=True)
    package_json = node_sandbox_package_json()
    package_path = node_sandbox / "package.json"
    current = package_path.read_text() if package_path.exists() else None
    desired = json.dumps(package_json, indent=2, ensure_ascii=False) + "\n"
    changed = current != desired
    if current != desired:
        package_path.write_text(desired)
    write_tsconfig(node_sandbox)
    if not install_node_deps:
        return None
    if (node_sandbox / "node_modules").exists() and not changed:
        return CheckResult(name="node:sandbox-install", ok=True, skipped=True, reason="node_modules already present")
    return npm_install(node_sandbox, timeout)


def link_node_sandbox(sample_dir: Path, node_sandbox: Path) -> None:
    node_modules = node_sandbox / "node_modules"
    if node_modules.exists() and not (sample_dir / "node_modules").exists():
        os.symlink(node_modules.resolve(), sample_dir / "node_modules", target_is_directory=True)
    for name in ("package-lock.json",):
        source = node_sandbox / name
        target = sample_dir / name
        if source.exists() and not target.exists():
            os.symlink(source.resolve(), target)


def verify_js_ts(
    sample: dict[str, Any],
    sample_dir: Path,
    timeout: float,
    install_node_deps: bool,
    node_sandbox: Path,
) -> list[CheckResult]:
    language = sample.get("language", "")
    ext = ts_extension(language)
    is_react = "react" in sample.get("code", "").lower() or "tsx" in sample.get("tests", "").lower() or "@testing-library/react" in sample.get("tests", "")
    solution_ext = "tsx" if ext == "ts" and is_react else ext
    test_ext = "tsx" if ext == "ts" and is_react else ext
    (sample_dir / f"solution.{solution_ext}").write_text(sample["code"].rstrip() + "\n")
    (sample_dir / f"solution.test.{test_ext}").write_text(normalize_js_ts_tests(sample["tests"], language).rstrip() + "\n")
    package = package_json_for(sample)
    jest_dom = "@testing-library/jest-dom" in package.get("devDependencies", {}) or uses_jest_dom_matchers(sample)
    write_json(sample_dir / "package.json", package)
    if ext == "ts":
        write_tsconfig(sample_dir, jest_dom=jest_dom)
    if "vitest" in package.get("scripts", {}).get("test", ""):
        if jest_dom:
            write_vitest_setup(sample_dir)
        write_vitest_config(sample_dir, is_react, jest_dom=jest_dom)
    checks: list[CheckResult] = []

    sandbox_install = prepare_node_sandbox(node_sandbox, timeout, install_node_deps)
    if sandbox_install is not None:
        checks.append(sandbox_install)
        if not sandbox_install.ok and not sandbox_install.skipped:
            return checks
    link_node_sandbox(sample_dir, node_sandbox)

    if install_node_deps:
        if not (sample_dir / "node_modules").exists():
            checks.append(CheckResult(name="node:sandbox-link", ok=False, skipped=True, reason="shared node_modules not available"))
            return checks

    if ext == "js":
        checks.append(run_command(["node", "--check", "solution.js"], sample_dir, timeout, "javascript:syntax-solution"))
        if "import " not in sample["tests"]:
            checks.append(run_command(["node", "--check", "solution.test.js"], sample_dir, timeout, "javascript:syntax-tests"))

    if shutil.which("npx"):
        if ext == "ts":
            checks.append(run_optional_node_command(["npx", "--no-install", "tsc", "--noEmit", "--pretty", "false"], sample_dir, timeout, "typescript:tsc"))
        if "test" in package.get("scripts", {}):
            script = package["scripts"]["test"]
            runner = script.split()[0]
            if script == "node --test":
                checks.append(run_command(["node", "--test", "solution.test.js"], sample_dir, timeout, "node:test"))
            else:
                checks.append(run_optional_node_command(["npx", "--no-install", runner, "run"] if runner == "vitest" else ["npx", "--no-install", runner, "--runInBand"], sample_dir, timeout, f"node:{runner}"))
    else:
        checks.append(CheckResult(name="node:npx", ok=False, skipped=True, reason="npx not found"))
    return checks


def verify_sample(
    sample: dict[str, Any],
    sample_dir: Path,
    timeout: float,
    install_node_deps: bool,
    node_sandbox: Path,
) -> dict[str, Any]:
    sample_dir.mkdir(parents=True, exist_ok=True)
    write_json(sample_dir / "sample.json", sample)
    language = sample.get("language", "").lower()
    checks: list[CheckResult]
    if language == "python":
        checks = verify_python(sample, sample_dir, timeout)
    elif language in {"typescript", "javascript", "ts", "js"}:
        checks = verify_js_ts(sample, sample_dir, timeout, install_node_deps, node_sandbox)
    else:
        checks = [CheckResult(name="language", ok=False, skipped=True, reason=f"unsupported language: {language}")]

    check_dicts = [check.as_dict() for check in checks]
    runnable = [check for check in checks if not check.skipped]
    # If all checks were skipped due to unavailable local tooling, the sample is
    # not verified but also not proven bad. Keep that distinction for curation.
    passed = bool(runnable) and all(check.ok for check in runnable)
    status = "passed" if passed else ("unverified" if not runnable else "failed")
    return {
        "passed": passed,
        "status": status,
        "checks": check_dicts,
        "workdir": str(sample_dir),
    }


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file))
    input_path = Path(env_value(args, "input", "INPUT", "deploy/distill_no-repair/phase1/outputs/pilot.jsonl"))
    output_path = Path(env_value(args, "output", "OUTPUT", "deploy/distill_no-repair/phase2/outputs/pilot.verified.jsonl"))
    workdir = Path(env_value(args, "workdir", "WORKDIR", "deploy/distill_no-repair/phase2/outputs/work"))
    node_sandbox = Path(env_value(args, "node_sandbox", "NODE_SANDBOX", "deploy/distill_no-repair/phase2/outputs/node_sandbox"))
    timeout = float(env_value(args, "timeout", "TIMEOUT", "60"))
    keep_workdir = env_bool(args, "keep_workdir", "KEEP_WORKDIR", True)
    install_node_deps = env_bool(args, "install_node_deps", "INSTALL_NODE_DEPS", False)

    ids_filter = load_ids(Path(args.ids_file)) if args.ids_file else None
    if args.offset < 0:
        raise SystemExit("--offset must be >= 0")
    if args.max_samples is not None and args.max_samples < 1:
        raise SystemExit("--max-samples must be >= 1")

    samples = load_jsonl(input_path)
    if ids_filter is not None:
        samples = [sample for sample in samples if sample.get("id") in ids_filter]
    if args.offset:
        samples = samples[args.offset:]
    if args.max_samples is not None:
        samples = samples[:args.max_samples]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)
    node_sandbox.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with output_path.open("w", encoding="utf-8") as out:
        for sample in samples:
            sample_dir = workdir / sample["id"]
            if sample_dir.exists():
                shutil.rmtree(sample_dir)
            result = verify_sample(sample, sample_dir, timeout, install_node_deps, node_sandbox)
            verified = dict(sample)
            verified["verification"] = {
                **(sample.get("verification") or {}),
                "phase2": result,
            }
            out.write(json.dumps(verified, ensure_ascii=False) + "\n")
            results.append({"id": sample["id"], **result})
            print(f"{sample['id']}: status={result['status']} passed={result['passed']} workdir={sample_dir}")
            if not keep_workdir:
                shutil.rmtree(sample_dir, ignore_errors=True)

    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "node_sandbox": str(node_sandbox),
        "ids_file": args.ids_file,
        "offset": args.offset,
        "max_samples": args.max_samples,
        "total": len(results),
        "passed": sum(1 for row in results if row["passed"]),
        "failed": sum(1 for row in results if row.get("status") == "failed"),
        "unverified": sum(1 for row in results if row.get("status") == "unverified"),
        "results": results,
    }
    write_json(output_path.with_suffix(".summary.json"), summary)
    print(json.dumps({k: summary[k] for k in ("total", "passed", "failed", "unverified")}, indent=2))


if __name__ == "__main__":
    main()
