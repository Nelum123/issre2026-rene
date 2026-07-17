#!/usr/bin/env python3
"""
Generate an LL(1) grammar JSON from converter.py grammar parameters.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


TERMINALS = tuple(string.ascii_lowercase)
REQUIRED_KEYS = (
    "nts_per_depth",
    "rules_per_def",
    "rule_len",
    "nt_per_rule",
    "star_count",
    "plus_count",
)


class GrammarGenError(ValueError):
    """Raised when generator parameters cannot produce the requested grammar."""


def is_nonterminal(symbol: str) -> bool:
    return symbol.rstrip("*+").startswith("$D")


def base_symbol(symbol: str) -> str:
    return symbol.rstrip("*+")


def _positive_int(params: dict[str, Any], key: str, allow_zero: bool = False) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise GrammarGenError(f"{key} must be an integer")
    if allow_zero:
        if value < 0:
            raise GrammarGenError(f"{key} must be non-negative")
    elif value <= 0:
        raise GrammarGenError(f"{key} must be positive")
    return value


def read_params(data: dict[str, Any]) -> dict[str, int]:
    if not isinstance(data, dict):
        raise GrammarGenError("input JSON must be an object")

    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise GrammarGenError("missing required fields: " + ", ".join(missing))

    params = {
        "nts_per_depth": _positive_int(data, "nts_per_depth", allow_zero=True),
        "rules_per_def": _positive_int(data, "rules_per_def"),
        "rule_len": _positive_int(data, "rule_len"),
        "nt_per_rule": _positive_int(data, "nt_per_rule", allow_zero=True),
        "star_count": _positive_int(data, "star_count", allow_zero=True),
        "plus_count": _positive_int(data, "plus_count", allow_zero=True),
    }

    if params["rules_per_def"] > len(TERMINALS):
        raise GrammarGenError("rules_per_def cannot exceed 26")
    if params["nt_per_rule"] >= params["rule_len"]:
        raise GrammarGenError("nt_per_rule must be less than rule_len")

    if params["nts_per_depth"] == 0 and params["nt_per_rule"] != 0:
        raise GrammarGenError("nt_per_rule must be 0 when nts_per_depth is 0")
    if params["nt_per_rule"] > params["nts_per_depth"]:
        raise GrammarGenError("nt_per_rule cannot exceed nts_per_depth")

    suffix_capacity = _suffix_capacity(params)
    if params["star_count"] + params["plus_count"] > suffix_capacity:
        raise GrammarGenError("star_count + plus_count exceeds available suffix positions")

    return params


def _depth_count(params: dict[str, int]) -> int:
    return 2 if params["nt_per_rule"] > 0 else 1


def _layer_sizes(params: dict[str, int]) -> tuple[int, int]:
    if params["nt_per_rule"] == 0:
        return params["nts_per_depth"], 0
    total = params["nts_per_depth"] * 2
    lower_count = max(params["nts_per_depth"], params["nt_per_rule"])
    upper_count = total - lower_count
    if upper_count > len(TERMINALS):
        upper_count = len(TERMINALS)
        lower_count = total - upper_count
    return upper_count, lower_count


def _suffix_capacity(params: dict[str, int]) -> int:
    if params["nts_per_depth"] == 0:
        return 0
    upper_count, _lower_count = _layer_sizes(params)
    generated_refs = upper_count * params["rules_per_def"] * params["nt_per_rule"]
    start_refs = upper_count
    return generated_refs + start_refs


def _layer_names(nts_per_depth: int, depth_count: int) -> list[list[str]]:
    next_id = 1
    layers: list[list[str]] = []
    for _ in range(depth_count):
        layer = []
        for _ in range(nts_per_depth):
            layer.append(f"$D{next_id}")
            next_id += 1
        layers.append(layer)
    return layers


def _terminal(rng: random.Random, reserved_prefix: str) -> str:
    choices = [symbol for symbol in TERMINALS if symbol != reserved_prefix]
    return rng.choice(choices)


def _apply_suffixes(grammar: dict[str, list[list[str]]], star_count: int, plus_count: int) -> None:
    suffixes = ["*"] * star_count + ["+"] * plus_count
    suffix_index = 0

    for lhs in grammar:
        for production in grammar[lhs]:
            for pos, symbol in enumerate(production):
                if suffix_index >= len(suffixes):
                    return
                if is_nonterminal(symbol):
                    production[pos] = production[pos] + suffixes[suffix_index]
                    suffix_index += 1


def generate_grammar(params: dict[str, Any], seed: int | str | None = None) -> dict[str, list[list[str]]]:
    p = read_params(params)
    rng = random.Random(seed)

    if p["nts_per_depth"] == 0:
        rule_prefixes = TERMINALS[: p["rules_per_def"]]
        grammar = {"$start": []}
        for prefix in rule_prefixes:
            production = [prefix]
            for _pos in range(1, p["rule_len"]):
                production.append(_terminal(rng, prefix))
            grammar["$start"].append(production)
        _apply_suffixes(grammar, p["star_count"], p["plus_count"])
        return grammar

    depth_count = _depth_count(p)
    if depth_count == 1:
        layers = _layer_names(p["nts_per_depth"], depth_count)
    else:
        upper_count, lower_count = _layer_sizes(p)
        if upper_count <= 0 or lower_count < p["nt_per_rule"]:
            raise GrammarGenError("not enough reachable non-terminals for nt_per_rule")
        if upper_count * p["rules_per_def"] * p["nt_per_rule"] < lower_count:
            raise GrammarGenError("not enough non-terminal references to make grammar reachable")
        lower_layer = [f"$D{i}" for i in range(1, lower_count + 1)]
        upper_layer = [f"$D{i}" for i in range(lower_count + 1, lower_count + upper_count + 1)]
        layers = [lower_layer, upper_layer]
    grammar: dict[str, list[list[str]]] = {}

    start_prefixes = TERMINALS[: len(layers[-1])]
    grammar["$start"] = [
        [prefix, nonterminal] for prefix, nonterminal in zip(start_prefixes, layers[-1])
    ]

    rule_prefixes = TERMINALS[: p["rules_per_def"]]
    lower_layer = layers[0]

    for depth_index, layer in enumerate(layers):
        for nt_index, name in enumerate(layer):
            productions = []
            for rule_index, prefix in enumerate(rule_prefixes):
                production = [prefix]
                for pos in range(1, p["rule_len"]):
                    if depth_index > 0 and pos <= p["nt_per_rule"]:
                        linear_index = (
                            nt_index * p["rules_per_def"] * p["nt_per_rule"]
                            + rule_index * p["nt_per_rule"]
                            + pos
                            - 1
                        )
                        ref_index = linear_index % len(lower_layer)
                        production.append(lower_layer[ref_index])
                    else:
                        production.append(_terminal(rng, prefix))
                productions.append(production)
            grammar[name] = productions

    _apply_suffixes(grammar, p["star_count"], p["plus_count"])
    return grammar


def build_call_graph(grammar: dict[str, list[list[str]]]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for lhs, productions in grammar.items():
        for production in productions:
            for symbol in production:
                if is_nonterminal(symbol):
                    graph[lhs].add(base_symbol(symbol))
    return graph


def reachable_nonterminals(grammar: dict[str, list[list[str]]]) -> set[str]:
    graph = build_call_graph(grammar)
    reachable = {"$start"}
    queue = deque(["$start"])
    while queue:
        current = queue.popleft()
        for target in sorted(graph.get(current, set())):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    return reachable


def is_ll1(grammar: dict[str, list[list[str]]]) -> bool:
    for productions in grammar.values():
        first_symbols = [base_symbol(production[0]) for production in productions if production]
        if len(first_symbols) != len(set(first_symbols)):
            return False
    return True


def grammar_stats(grammar: dict[str, list[list[str]]]) -> dict[str, int]:
    nonterminals = [name for name in grammar if name != "$start"]
    if not nonterminals:
        start_rules = grammar.get("$start", [])
        return {
            "nts_per_depth": 0,
            "rules_per_def": len(start_rules),
            "rule_len": len(start_rules[0]) if start_rules else 0,
            "nt_per_rule": 0,
            "star_count": sum(
                symbol.endswith("*")
                for productions_for_rule in grammar.values()
                for production in productions_for_rule
                for symbol in production
            ),
            "plus_count": sum(
                symbol.endswith("+")
                for productions_for_rule in grammar.values()
                for production in productions_for_rule
                for symbol in production
            ),
        }

    depth_count = 2 if any(
        is_nonterminal(symbol)
        for name in nonterminals
        for production in grammar[name]
        for symbol in production[1:]
    ) else 1
    nts_per_depth = len(nonterminals) // depth_count if depth_count else len(nonterminals)
    first_rules = grammar[nonterminals[0]] if nonterminals else []
    productions = [production for name in nonterminals for production in grammar[name]]

    return {
        "nts_per_depth": nts_per_depth,
        "rules_per_def": len(first_rules),
        "rule_len": len(first_rules[0]) if first_rules else 0,
        "nt_per_rule": max(
            (sum(1 for symbol in production[1:] if is_nonterminal(symbol)) for production in productions),
            default=0,
        ),
        "star_count": sum(
            symbol.endswith("*")
            for productions_for_rule in grammar.values()
            for production in productions_for_rule
            for symbol in production
        ),
        "plus_count": sum(
            symbol.endswith("+")
            for productions_for_rule in grammar.values()
            for production in productions_for_rule
            for symbol in production
        ),
    }


def validate_generated(grammar: dict[str, list[list[str]]], params: dict[str, int]) -> None:
    if "$start" not in grammar:
        raise GrammarGenError("grammar is missing $start")
    if not is_ll1(grammar):
        raise GrammarGenError("grammar is not LL(1)")
    unreachable = set(grammar) - reachable_nonterminals(grammar)
    if unreachable:
        raise GrammarGenError("grammar contains unreachable non-terminals")
    stats = grammar_stats(grammar)
    if stats != params:
        raise GrammarGenError(f"grammar stats do not match input: {stats} != {params}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an LL(1) grammar JSON from converter output JSON."
    )
    parser.add_argument("input", help="Input generator-parameters JSON file, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Output grammar JSON file. Defaults to stdout.")
    parser.add_argument("--seed", help="Optional seed for terminal randomization.")
    args = parser.parse_args()

    try:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        params = read_params(json.loads(text))
        grammar = generate_grammar(params, seed=args.seed)
        validate_generated(grammar, params)
        rendered = json.dumps(grammar, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, json.JSONDecodeError, GrammarGenError) as exc:
        print(f"grammar_gen.py: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
