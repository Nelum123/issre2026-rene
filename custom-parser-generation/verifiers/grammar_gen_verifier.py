#!/usr/bin/env python3
"""Independent verifier for grammar_gen.py outputs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


REQUIRED_KEYS = (
    "nts_per_depth",
    "rules_per_def",
    "rule_len",
    "nt_per_rule",
    "star_count",
    "plus_count",
)


class VerificationError(ValueError):
    pass


def base(symbol: str) -> str:
    return symbol.rstrip("*+")


def is_nonterminal(symbol: str) -> bool:
    return base(symbol).startswith("$")


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
                for rules in grammar.values()
                for production in rules
                for symbol in production
            ),
            "plus_count": sum(
                symbol.endswith("+")
                for rules in grammar.values()
                for production in rules
                for symbol in production
            ),
        }

    has_recursive_refs = any(
        is_nonterminal(symbol)
        for name in nonterminals
        for production in grammar[name]
        for symbol in production[1:]
    )
    depth_count = 2 if has_recursive_refs else 1
    productions = [production for name in nonterminals for production in grammar[name]]
    first_rules = grammar[nonterminals[0]] if nonterminals else []
    return {
        "nts_per_depth": len(nonterminals) // depth_count,
        "rules_per_def": len(first_rules),
        "rule_len": len(first_rules[0]) if first_rules else 0,
        "nt_per_rule": max(
            (sum(1 for symbol in production[1:] if is_nonterminal(symbol)) for production in productions),
            default=0,
        ),
        "star_count": sum(
            symbol.endswith("*")
            for rules in grammar.values()
            for production in rules
            for symbol in production
        ),
        "plus_count": sum(
            symbol.endswith("+")
            for rules in grammar.values()
            for production in rules
            for symbol in production
        ),
    }


def reachable(grammar: dict[str, list[list[str]]]) -> set[str]:
    graph: dict[str, set[str]] = defaultdict(set)
    for lhs, rules in grammar.items():
        for production in rules:
            for symbol in production:
                if is_nonterminal(symbol):
                    graph[lhs].add(base(symbol))
    seen = {"$start"}
    queue = deque(["$start"])
    while queue:
        current = queue.popleft()
        for target in sorted(graph.get(current, set())):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def verify_grammar(params: dict[str, Any], grammar: dict[str, Any]) -> dict[str, Any]:
    if tuple(params.keys()) != REQUIRED_KEYS:
        raise VerificationError("grammar parameter fields do not match the specification")
    if "$start" not in grammar:
        raise VerificationError("grammar is missing $start")
    for lhs, rules in grammar.items():
        if lhs != "$start" and not lhs.startswith("$D"):
            raise VerificationError(f"invalid nonterminal name: {lhs}")
        if not isinstance(rules, list) or not rules:
            raise VerificationError(f"{lhs} has no productions")
        first_symbols = []
        for production in rules:
            if not isinstance(production, list) or not production:
                raise VerificationError(f"{lhs} has an invalid production")
            first_symbols.append(base(production[0]))
            seen_nonterminals: set[str] = set()
            for symbol in production:
                raw = base(symbol)
                if is_nonterminal(symbol):
                    if raw not in grammar:
                        raise VerificationError(f"unknown nonterminal reference: {raw}")
                    if raw in seen_nonterminals:
                        raise VerificationError(f"{lhs} repeats nonterminal {raw} in one production")
                    seen_nonterminals.add(raw)
                elif len(raw) != 1 or raw < "a" or raw > "z":
                    raise VerificationError(f"invalid terminal: {symbol}")
                elif symbol.endswith(("*", "+")):
                    raise VerificationError(f"terminal suffix is not allowed: {symbol}")
        if len(first_symbols) != len(set(first_symbols)):
            raise VerificationError(f"{lhs} is not LL(1)")
    if set(grammar) != reachable(grammar):
        raise VerificationError("grammar contains unreachable nonterminals")
    stats = grammar_stats(grammar)
    if stats != params:
        raise VerificationError(f"grammar stats mismatch: {stats} != {params}")
    return {"ok": True, "grammar_stats": stats}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify grammar generator input/output JSON files.")
    parser.add_argument("params")
    parser.add_argument("grammar")
    args = parser.parse_args()
    try:
        params = json.loads(Path(args.params).read_text(encoding="utf-8"))
        grammar = json.loads(Path(args.grammar).read_text(encoding="utf-8"))
        print(json.dumps(verify_grammar(params, grammar), indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"grammar_gen_verifier.py: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
