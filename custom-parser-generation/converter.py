#!/usr/bin/env python3
"""
Convert requested parser attributes into grammar parameters.

Input is a JSON object containing any compatible subset of the attributes listed
in context/converter.md. Output is a JSON object with exactly the generator
parameters required by the project specification. Specified inputs map
deterministically to the outputs they affect; unspecified outputs are randomized.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
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

KEY_ALIASES = {
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
    "distinct_operators": "halstead_n1",
    "n2": "halstead_n2",
    "n_2": "halstead_n2",
    "halstead_n2": "halstead_n2",
    "distinct_operands": "halstead_n2",
    "N1": "halstead_N1",
    "N_1": "halstead_N1",
    "halstead_N1": "halstead_N1",
    "total_operators": "halstead_N1",
    "N2": "halstead_N2",
    "N_2": "halstead_N2",
    "halstead_N2": "halstead_N2",
    "total_operands": "halstead_N2",
    "hvoc": "halstead_vocabulary",
    "halstead_vocabulary": "halstead_vocabulary",
    "hlen": "halstead_length",
    "halstead_length": "halstead_length",
    "hvol": "halstead_volume",
    "halstead_volume": "halstead_volume",
    "hdif": "halstead_difficulty",
    "halstead_difficulty": "halstead_difficulty",
}

CONFLICT_GROUPS = {
    "attribute": (
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


class ConversionError(ValueError):
    """Raised when the input cannot be converted under the project rules."""


def _canonical_key(key: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", key).strip("_")
    return KEY_ALIASES.get(cleaned, KEY_ALIASES.get(cleaned.lower(), cleaned.lower()))


def _positive_number(value: Any, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConversionError(f"{key} must be a positive number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ConversionError(f"{key} must be a positive number")
    return value


def normalize_attributes(attributes: dict[str, Any]) -> dict[str, float]:
    if not isinstance(attributes, dict):
        raise ConversionError("input JSON must be an object")

    normalized: dict[str, float] = {}
    for raw_key, value in attributes.items():
        key = _canonical_key(raw_key)
        if key not in set(KEY_ALIASES.values()):
            raise ConversionError(f"unknown attribute: {raw_key}")
        if key in normalized:
            raise ConversionError(f"duplicate attribute after normalization: {raw_key}")
        normalized[key] = _positive_number(value, key)

    return normalized


def validate_attribute_combination(attributes: dict[str, float]) -> None:
    for group_name, keys in CONFLICT_GROUPS.items():
        present = [key for key in keys if key in attributes]
        if len(present) > 1:
            joined = ", ".join(present)
            raise ConversionError(f"invalid {group_name} combination: {joined}")


def apply_minimum_inputs(attributes: dict[str, float]) -> dict[str, float]:
    file_count = int(round(attributes.get("file_count", 1)))
    minimums = MINIMUM_INPUTS[1 if file_count <= 1 else 2]
    adjusted = dict(attributes)
    for key, minimum in minimums.items():
        if key in adjusted and adjusted[key] < minimum:
            adjusted[key] = float(minimum)
    return adjusted


def _source_value(
    attributes: dict[str, float],
    candidates: tuple[str, ...],
) -> float | None:
    for key in candidates:
        if key in attributes:
            return attributes[key]
    return None


def _scale(value: float, lo: int, hi: int, softness: float) -> int:
    if value <= 0:
        return lo
    scaled = lo + int(math.log1p(value) / softness)
    return max(lo, min(hi, scaled))


def _bounded_count(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(value))))


def _random_output(rng: random.Random, key: str, current: dict[str, int]) -> int:
    if key == "nts_per_depth":
        return 0
    if key == "rules_per_def":
        return 1
    if key == "rule_len":
        return 1
    if key == "nt_per_rule":
        return 0
    if key == "star_count":
        return 0
    if key == "plus_count":
        return 0
    raise AssertionError(f"unknown output key: {key}")


def _minimal_output(file_count: int) -> dict[str, int]:
    if file_count <= 2:
        nts_per_depth = max(0, file_count - 2)
        rules_per_def = 1
        rule_len = 1
        nt_per_rule = 0
    else:
        nts_per_depth = max(1, math.ceil((file_count - 2) / 2))
        rules_per_def = 2
        rule_len = 3
        nt_per_rule = 2 if nts_per_depth >= 2 else 1
    return {
        "nts_per_depth": nts_per_depth,
        "rules_per_def": rules_per_def,
        "rule_len": rule_len,
        "nt_per_rule": nt_per_rule,
        "star_count": 0,
        "plus_count": 0,
    }


def _suffix_capacity(current: dict[str, int]) -> int:
    nts_per_depth = current.get("nts_per_depth", 1)
    rules_per_def = current.get("rules_per_def", 1)
    nt_per_rule = current.get("nt_per_rule", 0)
    if nts_per_depth == 0:
        return 0
    if nt_per_rule <= 0:
        upper_count = nts_per_depth
    else:
        total = nts_per_depth * 2
        lower_count = max(nts_per_depth, nt_per_rule)
        upper_count = total - lower_count
        if upper_count > 26:
            upper_count = 26
    return upper_count + upper_count * rules_per_def * nt_per_rule


def _fit_suffix_counts(output: dict[str, int], fixed_star: bool, fixed_plus: bool) -> None:
    capacity = _suffix_capacity(output)
    if output["star_count"] + output["plus_count"] <= capacity:
        return
    if fixed_star and fixed_plus:
        output["star_count"] = min(output["star_count"], capacity)
        output["plus_count"] = max(0, capacity - output["star_count"])
    elif fixed_star:
        output["plus_count"] = max(0, capacity - output["star_count"])
    elif fixed_plus:
        output["star_count"] = max(0, capacity - output["plus_count"])
    else:
        output["star_count"] = min(output["star_count"], capacity)
        output["plus_count"] = max(0, capacity - output["star_count"])


def _ensure_reachable_shape(output: dict[str, int]) -> None:
    nts_per_depth = output["nts_per_depth"]
    if nts_per_depth <= 26:
        return

    if output["nt_per_rule"] <= 0:
        output["nt_per_rule"] = 1
    if output["rule_len"] <= output["nt_per_rule"]:
        output["rule_len"] = output["nt_per_rule"] + 1

    upper_count = 26
    lower_count = nts_per_depth * 2 - upper_count
    capacity = upper_count * output["rules_per_def"] * output["nt_per_rule"]
    if capacity >= lower_count:
        return

    needed_nt = math.ceil(lower_count / (upper_count * output["rules_per_def"]))
    if needed_nt > output["nt_per_rule"]:
        output["nt_per_rule"] = min(nts_per_depth, needed_nt)
        if output["rule_len"] <= output["nt_per_rule"]:
            output["rule_len"] = output["nt_per_rule"] + 1

    capacity = upper_count * output["rules_per_def"] * output["nt_per_rule"]
    if capacity >= lower_count:
        return

    needed_rules = math.ceil(lower_count / (upper_count * output["nt_per_rule"]))
    output["rules_per_def"] = min(26, max(output["rules_per_def"], needed_rules))


def _ensure_suffix_capacity(output: dict[str, int]) -> None:
    needed = output.get("star_count", 0) + output.get("plus_count", 0)
    if needed <= _suffix_capacity(output):
        return
    if output["nts_per_depth"] == 0:
        output["nts_per_depth"] = 1
    if needed > output["nts_per_depth"] and output["nt_per_rule"] == 0:
        output["nt_per_rule"] = 1
        if output["rule_len"] <= output["nt_per_rule"]:
            output["rule_len"] = output["nt_per_rule"] + 1

    _ensure_reachable_shape(output)
    while needed > _suffix_capacity(output) and output["rules_per_def"] < 26:
        output["rules_per_def"] += 1
    while needed > _suffix_capacity(output) and output["nt_per_rule"] < output["nts_per_depth"]:
        output["nt_per_rule"] += 1
        if output["rule_len"] <= output["nt_per_rule"]:
            output["rule_len"] = output["nt_per_rule"] + 1


def _rng(seed: int | str | None) -> random.Random:
    if seed is None:
        return random.Random()
    return random.Random(seed)


def _target_shape(stat: str, value: float, required_files: int) -> dict[str, int]:
    output = _minimal_output(required_files)
    if stat == "lloc":
        if value <= 120:
            output.update({"nts_per_depth": 0, "rules_per_def": 3, "rule_len": 17, "nt_per_rule": 0})
        else:
            output.update({"nts_per_depth": max(1, int(round(value / 3500))), "rules_per_def": 26, "rule_len": 64, "nt_per_rule": 16})
    elif stat == "file_size":
        if value <= 3:
            output.update({"nts_per_depth": 1, "rules_per_def": 1, "rule_len": 8, "nt_per_rule": 1, "star_count": 1})
        else:
            output.update({"nts_per_depth": max(1, int(round(value / 145))), "rules_per_def": 26, "rule_len": 64, "nt_per_rule": 16})
    elif stat in {"block_count", "cyclomatic_complexity"}:
        if value <= 12:
            output.update({"nts_per_depth": 0, "rules_per_def": 1, "rule_len": 4, "nt_per_rule": 0})
        else:
            output.update({"nts_per_depth": max(1, int(round(value / 3330))), "rules_per_def": 26, "rule_len": 64, "nt_per_rule": 16})
    elif stat in {"halstead_N1"}:
        output.update({"nts_per_depth": max(1, int(round(value / 3500))), "rules_per_def": 26, "rule_len": 64, "nt_per_rule": 16})
    elif stat in {"halstead_N2", "halstead_length"}:
        divisor = 17000 if stat == "halstead_length" else 13500
        output.update({"nts_per_depth": max(1, int(round(value / divisor))), "rules_per_def": 26, "rule_len": 64, "nt_per_rule": 16})
    elif stat == "halstead_volume":
        length_target = max(1, value / 8.0)
        output.update({"nts_per_depth": max(1, int(round(length_target / 17000))), "rules_per_def": 26, "rule_len": 64, "nt_per_rule": 16})
    elif stat in {"halstead_n2", "halstead_vocabulary"}:
        output.update({"nts_per_depth": max(1, int(round(value / 2))), "rules_per_def": 1, "rule_len": 10, "nt_per_rule": 9})
    elif stat in {"halstead_n1", "halstead_difficulty"}:
        output.update({"nts_per_depth": 1, "rules_per_def": 1, "rule_len": 8, "nt_per_rule": 1, "star_count": 1})
    elif stat in {"mrd", "max_depth"}:
        depth = max(1, int(round(value)))
        output.update({"nts_per_depth": max(1, depth), "rules_per_def": 1, "rule_len": max(2, min(64, depth + 1)), "nt_per_rule": 1})
    min_nts_for_files = max(0, math.ceil((required_files - 2) / 2))
    output["nts_per_depth"] = max(output["nts_per_depth"], min_nts_for_files)
    if required_files > 2 and output["nt_per_rule"] == 0:
        output["nt_per_rule"] = 1
    if output["nt_per_rule"] > output["nts_per_depth"]:
        output["nt_per_rule"] = output["nts_per_depth"]
    if output["rule_len"] <= output["nt_per_rule"]:
        output["rule_len"] = output["nt_per_rule"] + 1
    return output


def split_seed(attributes: dict[str, Any], cli_seed: int | str | None = None) -> tuple[dict[str, Any], int | str | None]:
    attributes = dict(attributes)
    json_seed = attributes.pop("seed", None)
    return attributes, cli_seed if cli_seed is not None else json_seed


def convert_attributes(attributes: dict[str, Any], seed: int | str | None = None) -> dict[str, int]:
    attributes, seed = split_seed(attributes, seed)
    normalized = normalize_attributes(attributes)
    validate_attribute_combination(normalized)
    normalized = apply_minimum_inputs(normalized)
    rng = _rng(seed)
    output: dict[str, int] = {}

    file_count = _source_value(normalized, ("file_count",))
    required_files = _bounded_count(file_count, 1, 100) if file_count is not None else 1
    if file_count is not None:
        output.update(_minimal_output(required_files))

    for group in CONFLICT_GROUPS["attribute"]:
        if group in normalized:
            output.update(_target_shape(group, normalized[group], required_files))
            break

    vocabulary = _source_value(
        normalized,
        ("halstead_vocabulary", "halstead_n2", "halstead_n1"),
    )
    size = _source_value(
        normalized,
        ("lloc", "file_size", "halstead_length", "halstead_volume"),
    )
    control = _source_value(
        normalized,
        ("block_count", "cyclomatic_complexity", "max_depth", "mrd"),
    )
    recursion = _source_value(
        normalized,
        ("mrd", "max_depth", "block_count", "cyclomatic_complexity"),
    )
    difficulty = _source_value(
        normalized,
        ("halstead_difficulty", "halstead_n1", "cyclomatic_complexity"),
    )
    operand_total = _source_value(
        normalized,
        ("halstead_N2", "halstead_n2", "cyclomatic_complexity"),
    )

    if file_count is not None and vocabulary is not None:
        output["nts_per_depth"] = max(
            output.get("nts_per_depth", 0),
            _bounded_count(file_count + math.log1p(vocabulary) / 2, 1, 100),
        )
    elif file_count is not None:
        output["nts_per_depth"] = output["nts_per_depth"]
    elif vocabulary is not None and "nts_per_depth" not in output:
        output["nts_per_depth"] = _bounded_count(math.log1p(vocabulary), 1, 26)
    elif "nts_per_depth" not in output:
        output["nts_per_depth"] = _random_output(rng, "nts_per_depth", output)

    if control is not None:
        output["rules_per_def"] = max(output.get("rules_per_def", 1), _scale(control, 1, 26, 1.4))
    elif "rules_per_def" not in output:
        output["rules_per_def"] = _random_output(rng, "rules_per_def", output)

    if size is not None:
        output["rule_len"] = max(output.get("rule_len", 1), _scale(size, 1, 64, 1.15))
    elif "rule_len" not in output:
        output["rule_len"] = _random_output(rng, "rule_len", output)

    if recursion is not None:
        desired_nt_per_rule = min(
            output["rule_len"] - 1,
            output["nts_per_depth"],
            _scale(recursion, 0, 16, 1.8),
        )
        output["nt_per_rule"] = max(output.get("nt_per_rule", 0), desired_nt_per_rule)
    elif "nt_per_rule" not in output:
        output["nt_per_rule"] = _random_output(rng, "nt_per_rule", output)
    if output["nts_per_depth"] == 0:
        output["nt_per_rule"] = 0
    if difficulty is not None:
        output["star_count"] = max(output.get("star_count", 0), _scale(difficulty, 0, 32, 1.7))
    elif "star_count" not in output:
        output["star_count"] = _random_output(rng, "star_count", output)

    if operand_total is not None:
        output["plus_count"] = max(output.get("plus_count", 0), _scale(operand_total, 0, 32, 1.7))
    elif "plus_count" not in output:
        output["plus_count"] = _random_output(rng, "plus_count", output)
    _ensure_reachable_shape(output)
    _ensure_suffix_capacity(output)
    _fit_suffix_counts(output, difficulty is not None, operand_total is not None)
    _ensure_reachable_shape(output)
    _ensure_suffix_capacity(output)
    if output["nts_per_depth"] > 100:
        output["nts_per_depth"] = 100
    if output["rule_len"] > 64:
        output["rule_len"] = 64
    if output["rules_per_def"] > 26:
        output["rules_per_def"] = 26
    output["nt_per_rule"] = min(output["nt_per_rule"], output["nts_per_depth"], output["rule_len"] - 1)
    _ensure_reachable_shape(output)
    if output["rule_len"] > 64:
        output["rule_len"] = 64
        output["nt_per_rule"] = min(output["nt_per_rule"], output["rule_len"] - 1)
    while output["nts_per_depth"] > 26 and output["nt_per_rule"] > 0:
        total = output["nts_per_depth"] * 2
        lower_count = total - 26
        capacity = 26 * output["rules_per_def"] * output["nt_per_rule"]
        if capacity >= lower_count or output["rules_per_def"] >= 26:
            break
        output["rules_per_def"] += 1
    _fit_suffix_counts(output, difficulty is not None, operand_total is not None)

    depth_count = 2 if output["nt_per_rule"] > 0 else 1
    parser_functions = 1 + output["nts_per_depth"] * depth_count
    max_files = 2 if parser_functions == 1 else parser_functions + 1
    if required_files > max_files:
        raise ConversionError("file_count exceeds available parser functions")

    return {key: output[key] for key in OUTPUT_KEYS}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert parser attributes JSON into grammar parameters JSON."
    )
    parser.add_argument("input", help="Input attributes JSON file, or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON file. Defaults to stdout.",
    )
    parser.add_argument(
        "--seed",
        help="Optional seed for randomized unspecified outputs.",
    )
    args = parser.parse_args()

    try:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        output = convert_attributes(json.loads(text), seed=args.seed)
        rendered = json.dumps(output, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, json.JSONDecodeError, ConversionError) as exc:
        print(f"converter.py: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
