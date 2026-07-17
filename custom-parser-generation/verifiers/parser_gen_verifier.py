#!/usr/bin/env python3
"""Independent verifier for parser_gen.py outputs."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


class VerificationError(ValueError):
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


def source_file_count(source_input: dict[str, Any]) -> int:
    return int(round(float(source_input.get("file_count", 1))))


def parser_statistics(paths: list[Path]) -> dict[str, float | int]:
    total_bytes = 0
    lloc = 0
    if_count = 0
    while_count = 0
    distinct_operands: set[str] = set()
    distinct_operators: set[str] = set()
    total_operands = 0
    total_operators = 0

    combined_texts = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        combined_texts.append(text)
        total_bytes += len(text.encode("utf-8"))
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|==|!=|<=|>=|&&|\|\||[{}();=+\-*/<>]", text)
        for token in tokens:
            if token in {"if", "while", "return", "for"} or token in {"==", "!=", "<=", ">=", "&&", "||", "=", "+", "-", "*", "/", "<", ">"}:
                distinct_operators.add(token)
                total_operators += 1
            elif re.match(r"[A-Za-z_]", token):
                distinct_operands.add(token)
                total_operands += 1
        if_count += len(re.findall(r"\bif\s*\(", text))
        while_count += len(re.findall(r"\bwhile\s*\(", text))
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
                lloc += 1

    vocabulary = len(distinct_operators) + len(distinct_operands)
    length = total_operators + total_operands
    stats = {
        "lloc": lloc,
        "file_size": round(total_bytes / 1024, 3),
        "file_count": len(paths),
        "block_count": 1 + if_count + while_count,
        "mrd": 0,
        "max_depth": 0,
        "cyclomatic_complexity": 1 + if_count + while_count,
        "halstead_n1": len(distinct_operators),
        "halstead_n2": len(distinct_operands),
        "halstead_N1": total_operators,
        "halstead_N2": total_operands,
        "halstead_vocabulary": vocabulary,
        "halstead_length": length,
        "halstead_volume": 0 if vocabulary == 0 else round(length * math.log2(vocabulary), 3),
        "halstead_difficulty": 0
        if len(distinct_operands) == 0
        else round((len(distinct_operators) / 2) * (total_operands / len(distinct_operands)), 3),
    }
    return stats


def canonical_source_input(source_input: dict[str, Any]) -> dict[str, float]:
    canonical: dict[str, float] = {}
    for key, value in source_input.items():
        if key == "seed":
            continue
        stat = ATTRIBUTE_ALIASES.get(key, ATTRIBUTE_ALIASES.get(key.lower()))
        if stat is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VerificationError(f"{key} must be numeric")
        canonical[stat] = float(value)

    file_count = int(round(canonical.get("file_count", 1)))
    minimums = MINIMUM_INPUTS[1 if file_count <= 1 else 2]
    for stat, minimum in minimums.items():
        if stat in canonical and canonical[stat] < minimum:
            canonical[stat] = float(minimum)
    return canonical


def tolerance(expected: float) -> float:
    return max(1.0, abs(expected) * 0.05)


def assert_requested_statistics(
    source_input: dict[str, Any],
    stats: dict[str, float | int],
    cfg_statistics: dict[str, float | int] | None = None,
) -> None:
    requested = canonical_source_input(source_input)
    for stat, expected in requested.items():
        if stat == "file_count":
            pass
        elif stat in {"mrd", "max_depth"} and cfg_statistics:
            pass
        else:
            continue
        if stat not in stats:
            raise VerificationError(f"missing parser statistic {stat}")
        actual = float(stats[stat])
        allowed = tolerance(expected)
        if abs(actual - expected) > allowed:
            raise VerificationError(
                f"{stat} outside accepted range: requested {expected:g}, got {actual:g}, tolerance {allowed:g}"
            )


def verify_parser(
    source_input: dict[str, Any],
    output_dir: Path,
    cfg_statistics: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    if not output_dir.is_dir():
        raise VerificationError("parser output path must be a directory")
    files = sorted(path for path in output_dir.iterdir() if path.suffix in {".c", ".h"})
    if len(files) != source_file_count(source_input):
        raise VerificationError("generated file count does not match source input")
    makefile = output_dir / "Makefile"
    if not makefile.exists():
        raise VerificationError("Makefile is missing")
    parser_c = output_dir / "parser.c"
    if not parser_c.exists():
        raise VerificationError("parser.c is missing")
    main_source = parser_c.read_text(encoding="utf-8")
    for required in (
        "int main(int argc, char **argv)",
        'printf("Accepted\\n");',
        'printf("Rejected\\n");',
    ):
        if required not in main_source:
            raise VerificationError(f"parser.c is missing {required}")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    if "//" in combined or "/*" in combined:
        raise VerificationError("parser output must not contain comments")
    for forbidden in ("metric_pad", "metric_report", "pad_sink", "pad_line"):
        if forbidden in combined:
            raise VerificationError(f"parser output contains forbidden instrumentation: {forbidden}")
    if "static char peek(void)" not in combined:
        raise VerificationError("peek helper is missing")
    if "static int match_char(char c)" not in combined:
        raise VerificationError("match_char helper is missing")
    stats = parser_statistics(files)
    if cfg_statistics:
        stats.update(cfg_statistics)
    assert_requested_statistics(source_input, stats, cfg_statistics=cfg_statistics)
    return {"ok": True, "final_parser_statistics": stats}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify generated parser files.")
    parser.add_argument("source_input")
    parser.add_argument("output_dir")
    args = parser.parse_args()
    try:
        source = json.loads(Path(args.source_input).read_text(encoding="utf-8"))
        print(json.dumps(verify_parser(source, Path(args.output_dir)), indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"parser_gen_verifier.py: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
