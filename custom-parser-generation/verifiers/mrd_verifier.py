#!/usr/bin/env python3
"""Verifier for parser MRD and Max Depth using GCC CFG dumps."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class MRDVerificationError(ValueError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_extra_calculator() -> Any:
    extra_path = repo_root() / "extra" / "calculate_mrd.py"
    spec = importlib.util.spec_from_file_location("extra_calculate_mrd", extra_path)
    if spec is None or spec.loader is None:
        raise MRDVerificationError(f"cannot load MRD calculator from {extra_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_files(parser_dir: Path) -> list[Path]:
    files = sorted(parser_dir.glob("*.c"))
    if not files:
        raise MRDVerificationError(f"no C source files found in {parser_dir}")
    return files


def clean_dump_workspace(parser_dir: Path, dump_dir: Path, binary_name: str) -> None:
    if dump_dir.exists():
        shutil.rmtree(dump_dir)
    dump_dir.mkdir(parents=True)
    for pattern in ("*.cfg", "*.cfg.dot", "*.cgraph", "*.ipa-cgraph", "*.o"):
        for path in parser_dir.glob(pattern):
            path.unlink()
    binary = parser_dir / binary_name
    if binary.exists():
        binary.unlink()


def build_gcc_dumps(
    parser_dir: Path,
    dump_dir: Path | None = None,
    binary_name: str = "mrd_test_bin.exe",
    gcc: str = "gcc",
) -> Path:
    parser_dir = parser_dir.resolve()
    if not parser_dir.is_dir():
        raise MRDVerificationError(f"parser path must be a directory: {parser_dir}")
    dump_dir = (dump_dir or parser_dir / "mrd_dumps").resolve()
    clean_dump_workspace(parser_dir, dump_dir, binary_name)
    files = [path.name for path in source_files(parser_dir)]
    cmd = [
        gcc,
        "-O0",
        "-g0",
        "-fdump-tree-cfg-graph",
        "-fdump-ipa-cgraph",
        *files,
        "-o",
        binary_name,
    ]
    try:
        subprocess.run(
            cmd,
            cwd=parser_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise MRDVerificationError("gcc is required to build CFG dumps") from exc
    except subprocess.CalledProcessError as exc:
        raise MRDVerificationError(exc.stderr.strip() or "gcc failed to build CFG dumps") from exc

    for pattern in ("*.cfg", "*.cfg.dot", "*.cgraph", "*.ipa-cgraph"):
        for path in parser_dir.glob(pattern):
            path.replace(dump_dir / path.name)
    return dump_dir


def max_depth_from_distribution(result: dict[str, Any]) -> int:
    distribution = result.get("reachable_depth_distribution", [])
    return max((int(row.get("depth", 0)) for row in distribution), default=0)


def calculate_mrd(parser_dir: Path, entry: str = "main", dump_dir: Path | None = None) -> dict[str, Any]:
    dump_path = build_gcc_dumps(parser_dir, dump_dir=dump_dir)
    calculator = load_extra_calculator()
    functions, source_kind = calculator.find_functions(dump_path)
    result = calculator.compute_mrd(functions, entry)
    return {
        "MRD": result["MRD"],
        "max_depth": max_depth_from_distribution(result),
        "blocks": result["blocks"],
        "conditional_statements": result["conditional_statements"],
        "sum_reachable_depth": result["sum_reachable_depth"],
        "reachable_depth_distribution": result["reachable_depth_distribution"],
        "dump_dir": str(dump_path),
        "source_kind": source_kind,
    }


def within_tolerance(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= int(abs(expected) * 0.05)


def verify_mrd(
    parser_dir: Path,
    expected_mrd: float | None = None,
    expected_max_depth: float | None = None,
    entry: str = "main",
) -> dict[str, Any]:
    result = calculate_mrd(parser_dir, entry=entry)
    failures: list[str] = []
    if expected_mrd is not None and not within_tolerance(float(result["MRD"]), expected_mrd):
        failures.append(f"MRD expected {expected_mrd:g}, got {float(result['MRD']):g}")
    if expected_max_depth is not None and not within_tolerance(float(result["max_depth"]), expected_max_depth):
        failures.append(f"Max Depth expected {expected_max_depth:g}, got {float(result['max_depth']):g}")
    if failures:
        raise MRDVerificationError("; ".join(failures))
    return {"ok": True, "mrd_statistics": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate and verify MRD/Max Depth for a parser directory.")
    parser.add_argument("parser_dir")
    parser.add_argument("--entry", default="main")
    parser.add_argument("--expected-mrd", type=float)
    parser.add_argument("--expected-max-depth", type=float)
    parser.add_argument("--json-out")
    args = parser.parse_args()
    try:
        output = verify_mrd(
            Path(args.parser_dir),
            expected_mrd=args.expected_mrd,
            expected_max_depth=args.expected_max_depth,
            entry=args.entry,
        )
        rendered = json.dumps(output, indent=2) + "\n"
        if args.json_out:
            Path(args.json_out).write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, MRDVerificationError) as exc:
        print(f"mrd_verifier.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
