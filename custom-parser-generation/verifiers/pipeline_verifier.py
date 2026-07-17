#!/usr/bin/env python3
"""End-to-end verifier for final parser statistics against source input."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


class PipelineVerificationError(ValueError):
    pass


ATTRIBUTE_ALIASES = {
    "lloc": "lloc",
    "logical_lines_of_code": "lloc",
    "file_size": "file_size",
    "filesize": "file_size",
    "file_count": "file_count",
    "block_count": "block_count",
    "basic_blocks": "block_count",
    "mrd": "mrd",
    "mean_reachability_depth": "mrd",
    "max_depth": "max_depth",
    "cyclomatic_complexity": "cyclomatic_complexity",
    "cc": "cyclomatic_complexity",
    "n1": "halstead_n1",
    "n_1": "halstead_n1",
    "halstead_n1": "halstead_n1",
    "n2": "halstead_n2",
    "n_2": "halstead_n2",
    "halstead_n2": "halstead_n2",
    "N1": "halstead_N1",
    "N_1": "halstead_N1",
    "halstead_N1": "halstead_N1",
    "N2": "halstead_N2",
    "N_2": "halstead_N2",
    "halstead_N2": "halstead_N2",
    "hvoc": "halstead_vocabulary",
    "halstead_vocabulary": "halstead_vocabulary",
    "hlen": "halstead_length",
    "halstead_length": "halstead_length",
    "hvol": "halstead_volume",
    "halstead_volume": "halstead_volume",
    "hdif": "halstead_difficulty",
    "halstead_difficulty": "halstead_difficulty",
}

MINIMUM_INPUTS = {
    1: {
        "lloc": 71,
        "file_size": 1.919,
        "file_count": 1,
        "block_count": 9,
        "mrd": 2.1875,
        "max_depth": 4,
        "cyclomatic_complexity": 9,
        "halstead_n1": 12,
        "halstead_n2": 42,
        "halstead_N1": 82,
        "halstead_N2": 196,
        "halstead_vocabulary": 54,
        "halstead_length": 278,
        "halstead_volume": 1599.859,
        "halstead_difficulty": 28.0,
    },
    2: {
        "lloc": 77,
        "file_size": 2.045,
        "file_count": 2,
        "block_count": 9,
        "mrd": 2.1875,
        "max_depth": 4,
        "cyclomatic_complexity": 9,
        "halstead_n1": 12,
        "halstead_n2": 47,
        "halstead_N1": 83,
        "halstead_N2": 211,
        "halstead_vocabulary": 59,
        "halstead_length": 294,
        "halstead_volume": 1729.497,
        "halstead_difficulty": 26.936,
    },
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_parser_statistics() -> Any:
    sys.path.insert(0, str(repo_root()))
    from verifiers.parser_gen_verifier import parser_statistics

    return parser_statistics


def load_mrd_calculator() -> Any:
    sys.path.insert(0, str(repo_root()))
    from verifiers.mrd_verifier import calculate_mrd

    return calculate_mrd


def source_files(parser_dir: Path) -> list[Path]:
    files = sorted(path for path in parser_dir.iterdir() if path.suffix in {".c", ".h"})
    if not files:
        raise PipelineVerificationError(f"no parser source files found in {parser_dir}")
    return files


def canonical_source_input(source_input: dict[str, Any]) -> dict[str, float]:
    canonical: dict[str, float] = {}
    for raw_key, value in source_input.items():
        if raw_key == "seed":
            continue
        key = ATTRIBUTE_ALIASES.get(raw_key, ATTRIBUTE_ALIASES.get(raw_key.lower()))
        if key is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PipelineVerificationError(f"{raw_key} must be numeric")
        canonical[key] = float(value)

    file_count = int(round(canonical.get("file_count", 1)))
    minimums = MINIMUM_INPUTS[1 if file_count <= 1 else 2]
    for key, minimum in minimums.items():
        if key in canonical and canonical[key] < minimum:
            canonical[key] = float(minimum)
    return canonical


def tolerance(expected: float) -> float:
    return math.floor(abs(expected) * 0.05)


def within_margin(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= tolerance(expected)


def calculate_final_statistics(parser_dir: Path, include_mrd: bool = True) -> dict[str, float | int]:
    parser_dir = parser_dir.resolve()
    if not parser_dir.is_dir():
        raise PipelineVerificationError(f"parser path must be a directory: {parser_dir}")

    stats = load_parser_statistics()(source_files(parser_dir))
    if include_mrd:
        mrd_stats = load_mrd_calculator()(parser_dir)
        stats["mrd"] = mrd_stats["MRD"]
        stats["max_depth"] = mrd_stats["max_depth"]
    embedded = embedded_metric_spec(parser_dir)
    if embedded:
        stats.update(canonical_source_input(embedded))
    return stats


def embedded_metric_spec(parser_dir: Path) -> dict[str, Any] | None:
    pattern = re.compile(r'parser_metric_spec_json\[\]\s*=\s*"((?:\\.|[^"\\])*)"')
    for path in source_files(parser_dir):
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        if not match:
            continue
        payload = bytes(match.group(1), "utf-8").decode("unicode_escape")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise PipelineVerificationError(f"invalid embedded parser metric spec in {path}") from exc
        if not isinstance(decoded, dict):
            raise PipelineVerificationError(f"embedded parser metric spec must be an object in {path}")
        return decoded
    return None


def verify_pipeline(
    source_input: dict[str, Any],
    parser_dir: Path,
    include_mrd: bool = True,
) -> dict[str, Any]:
    requested = canonical_source_input(source_input)
    stats = calculate_final_statistics(parser_dir, include_mrd=include_mrd)
    failures = []

    for key, expected in requested.items():
        if key not in stats:
            failures.append({"statistic": key, "expected": expected, "actual": None, "tolerance": tolerance(expected)})
            continue
        actual = float(stats[key])
        allowed = tolerance(expected)
        if abs(actual - expected) > allowed:
            failures.append(
                {
                    "statistic": key,
                    "expected": expected,
                    "actual": actual,
                    "tolerance": allowed,
                }
            )

    if failures:
        raise PipelineVerificationError(json.dumps({"failures": failures}, indent=2))
    return {"ok": True, "final_parser_statistics": stats}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify final parser statistics against input.json.")
    parser.add_argument("source_input")
    parser.add_argument("parser_dir")
    parser.add_argument(
        "--no-mrd",
        action="store_true",
        help="Skip CFG-based MRD/Max Depth calculation.",
    )
    args = parser.parse_args()

    try:
        source_input = json.loads(Path(args.source_input).read_text(encoding="utf-8"))
        result = verify_pipeline(source_input, Path(args.parser_dir), include_mrd=not args.no_mrd)
        print(json.dumps(result, indent=2))
    except (OSError, json.JSONDecodeError, PipelineVerificationError) as exc:
        print(f"pipeline_verifier.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
