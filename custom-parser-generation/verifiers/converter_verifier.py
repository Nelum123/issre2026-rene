#!/usr/bin/env python3
"""Independent verifier for converter.py outputs."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


OUTPUT_KEYS = (
    "nts_per_depth",
    "rules_per_def",
    "rule_len",
    "nt_per_rule",
    "star_count",
    "plus_count",
)

CONFLICT_GROUPS = (
    (
        "lloc",
        "file_size",
        "block_count",
        "mrd",
        "max_depth",
        "cyclomatic_complexity",
        "halstead_n1",
        "halstead_n2",
        "halstead_N1",
        "halstead_N2",
        "halstead_vocabulary",
        "halstead_length",
        "halstead_volume",
        "halstead_difficulty",
    ),
)

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


class VerificationError(ValueError):
    pass


def suffix_capacity(params: dict[str, int]) -> int:
    if params["nts_per_depth"] == 0:
        return 0
    if params["nt_per_rule"] <= 0:
        upper_count = params["nts_per_depth"]
    else:
        total = params["nts_per_depth"] * 2
        lower_count = max(params["nts_per_depth"], params["nt_per_rule"])
        upper_count = total - lower_count
        if upper_count > 26:
            upper_count = 26
    return upper_count + upper_count * params["rules_per_def"] * params["nt_per_rule"]


def effective_source_input(source_input: dict[str, Any]) -> dict[str, Any]:
    file_count = int(round(float(source_input.get("file_count", 1))))
    minimums = MINIMUM_INPUTS[1 if file_count <= 1 else 2]
    adjusted = dict(source_input)
    for key, minimum in minimums.items():
        if key in adjusted and isinstance(adjusted[key], (int, float)) and adjusted[key] < minimum:
            adjusted[key] = minimum
    return adjusted


def verify_converter_output(source_input: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    source_input = effective_source_input(source_input)
    if tuple(output.keys()) != OUTPUT_KEYS:
        raise VerificationError("converter output fields do not match the specification")
    for key in OUTPUT_KEYS:
        if isinstance(output[key], bool) or not isinstance(output[key], int):
            raise VerificationError(f"{key} must be an integer")

    for group in CONFLICT_GROUPS:
        present = [key for key in group if key in source_input]
        if len(present) > 1:
            raise VerificationError("source input contains conflicting fields: " + ", ".join(present))

    if not (0 <= output["nts_per_depth"] <= 100):
        raise VerificationError("nts_per_depth out of range")
    if not (1 <= output["rules_per_def"] <= 26):
        raise VerificationError("rules_per_def out of range")
    if not (1 <= output["rule_len"] <= 64):
        raise VerificationError("rule_len out of range")
    if not (0 <= output["nt_per_rule"] < output["rule_len"]):
        raise VerificationError("nt_per_rule must be less than rule_len")
    if output["nts_per_depth"] == 0 and output["nt_per_rule"] != 0:
        raise VerificationError("nt_per_rule must be 0 when nts_per_depth is 0")
    if output["nt_per_rule"] > output["nts_per_depth"]:
        raise VerificationError("nt_per_rule cannot exceed nts_per_depth")
    if output["star_count"] < 0 or output["plus_count"] < 0:
        raise VerificationError("suffix counts must be non-negative")
    if output["star_count"] + output["plus_count"] > suffix_capacity(output):
        raise VerificationError("suffix counts exceed grammar capacity")

    file_count = int(round(float(source_input.get("file_count", 1))))
    parser_functions = 1 + output["nts_per_depth"] * (2 if output["nt_per_rule"] > 0 else 1)
    max_files = 2 if parser_functions == 1 else parser_functions + 1
    if file_count > max_files:
        raise VerificationError("file_count exceeds available parser functions")

    return {"ok": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify converter input/output JSON files.")
    parser.add_argument("source_input")
    parser.add_argument("converter_output")
    args = parser.parse_args()
    try:
        source = json.loads(Path(args.source_input).read_text(encoding="utf-8"))
        output = json.loads(Path(args.converter_output).read_text(encoding="utf-8"))
        print(json.dumps(verify_converter_output(source, output), indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"converter_verifier.py: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
