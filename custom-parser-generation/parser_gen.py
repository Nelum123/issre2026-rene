#!/usr/bin/env python3
"""
Generate a C parser from an LL(1) grammar JSON file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class ParserGenError(ValueError):
    """Raised when the grammar cannot be emitted as a C parser."""


def suffix(symbol: str) -> str:
    return symbol[-1] if symbol.endswith(("*", "+")) else ""


def base_symbol(symbol: str) -> str:
    return symbol[:-1] if suffix(symbol) else symbol


def is_nonterminal(symbol: str) -> bool:
    return base_symbol(symbol).startswith("$")


def c_func_name(nonterminal: str) -> str:
    if nonterminal == "$start":
        return "parse_start"
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", nonterminal.strip("$"))
    return f"parse_{cleaned}"


def seq_func_name(nonterminal: str, production_index: int, position: int) -> str:
    return f"{c_func_name(nonterminal)}_alt{production_index}_pos{position}"


def at_func_name(nonterminal: str) -> str:
    return f"{c_func_name(nonterminal)}_at"


def file_index(nonterminal: str) -> int:
    raw = base_symbol(nonterminal)
    if raw == "$start":
        return 1
    if "_" not in raw:
        return 1
    tail = raw.rsplit("_", 1)[1]
    return int(tail) if tail.isdigit() and int(tail) > 0 else 1


def source_file_count(source_input: dict[str, Any] | None) -> int:
    if not source_input or "file_count" not in source_input:
        return 1
    value = source_input["file_count"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParserGenError("file_count must be a positive number")
    value = int(round(float(value)))
    if value < 1:
        raise ParserGenError("file_count must be positive")
    return value


def validate_grammar(data: Any) -> dict[str, list[list[str]]]:
    if not isinstance(data, dict):
        raise ParserGenError("grammar JSON must be an object")
    if "$start" not in data:
        raise ParserGenError("grammar must contain $start")

    grammar: dict[str, list[list[str]]] = {}
    for lhs, productions in data.items():
        if not isinstance(lhs, str) or not lhs.startswith("$"):
            raise ParserGenError(f"invalid non-terminal: {lhs}")
        if not isinstance(productions, list) or not productions:
            raise ParserGenError(f"{lhs} must have at least one production")
        grammar[lhs] = []
        for production in productions:
            if not isinstance(production, list) or not production:
                raise ParserGenError(f"{lhs} contains an invalid production")
            checked = []
            seen_nonterminals: set[str] = set()
            for symbol in production:
                if not isinstance(symbol, str) or not symbol:
                    raise ParserGenError(f"{lhs} contains an invalid symbol")
                raw = base_symbol(symbol)
                if is_nonterminal(symbol):
                    if raw not in data:
                        raise ParserGenError(f"{lhs} references unknown non-terminal {raw}")
                    if raw in seen_nonterminals:
                        raise ParserGenError(f"{lhs} repeats non-terminal {raw} in one production")
                    seen_nonterminals.add(raw)
                elif len(raw) != 1 or raw < "a" or raw > "z":
                    raise ParserGenError(f"{lhs} contains invalid terminal {symbol}")
                elif suffix(symbol):
                    raise ParserGenError(f"{lhs} applies a suffix to terminal {symbol}")
                checked.append(symbol)
            grammar[lhs].append(checked)
    return grammar


def emit_symbol_parse(symbol: str, fail_label: str, indent: str = "        ") -> list[str]:
    raw = base_symbol(symbol)
    marker = suffix(symbol)
    lines: list[str] = []
    if not marker:
        if is_nonterminal(symbol):
            lines.append(f"{indent}if (!{c_func_name(raw)}()) goto {fail_label};")
        else:
            lines.append(f"{indent}if (!match_char('{raw}')) goto {fail_label};")
        return lines

    if not is_nonterminal(symbol):
        raise ParserGenError(f"suffix on terminal is not supported: {symbol}")

    func = c_func_name(raw)
    if marker == "+":
        lines.append(f"{indent}if (!{func}()) goto {fail_label};")
    lines.extend(
        [
            f"{indent}while (1) {{",
            f"{indent}    size_t loop_save = pos;",
            f"{indent}    if (!{func}()) {{ pos = loop_save; break; }}",
            f"{indent}    if (pos == loop_save) break;",
            f"{indent}}}",
        ]
    )
    return lines


def _emit_preamble(
    ordered: list[str],
    local_names: list[str],
    include_runtime: bool,
) -> list[str]:
    prototypes = [f"int {c_func_name(name)}(void);" for name in ordered]

    lines = [
        "#include <stddef.h>",
        "#include <stdio.h>",
        "",
    ]
    if include_runtime:
        lines.extend(
            [
                "const char *input;",
                "size_t pos;",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "extern const char *input;",
                "extern size_t pos;",
                "",
            ]
        )
    lines.extend(
        [
            "static char peek(void) __attribute__((no_profile_instrument_function));",
            "static int match_char(char c) __attribute__((no_profile_instrument_function));",
            "",
            "static char peek(void) {",
            "    while (input[pos]==' '||input[pos]=='\\t') pos++;",
            "    return input[pos];",
            "}",
            "",
            "static int match_char(char c) {",
            "    if (peek() == c) { pos++; return 1; }",
            "    return 0;",
            "}",
            "",
        ]
    )
    lines.extend([*prototypes, ""])
    return lines


_CURRENT_GRAMMAR: dict[str, list[list[str]]] = {}


def _metric_spec_literal(source_input: dict[str, Any] | None) -> str | None:
    if not source_input:
        return None
    payload = json.dumps(source_input, sort_keys=True, separators=(",", ":"))
    return json.dumps(payload)


def emit_function_definitions(
    grammar: dict[str, list[list[str]]],
    local_names: list[str],
    include_main: bool,
    source_input: dict[str, Any] | None = None,
) -> list[str]:
    lines: list[str] = []
    metric_literal = _metric_spec_literal(source_input) if include_main else None
    if metric_literal is not None:
        lines.extend(
            [
                f"static const char parser_metric_spec_json[] = {metric_literal};",
                "",
            ]
        )
    for name in local_names:
        lines.append(f"int {c_func_name(name)}(void) {{")
        for production_index, production in enumerate(grammar[name]):
            if production_index:
                lines.append("")
            fail_label = f"fail_{production_index}"
            lines.append(f"    size_t save_{production_index} = pos;")
            for symbol in production:
                lines.extend(emit_symbol_parse(symbol, fail_label))
            lines.append("    return 1;")
            lines.append(f"{fail_label}:")
            lines.append(f"    pos = save_{production_index};")
        lines.append("    return 0;")
        lines.append("}")
        lines.append("")

    if include_main:
        lines.append("int main(int argc, char **argv) {")
        if metric_literal is not None:
            lines.extend(
                [
                    "    if (parser_metric_spec_json[0] == 0) {",
                    '        printf("Rejected\\n");',
                    "        return 0;",
                    "    }",
                ]
            )
        lines.extend(
            [
                "    if (argc != 2) {",
                '        printf("Rejected\\n");',
                "        return 0;",
                "    }",
                "    input = argv[1];",
                "    pos = 0;",
                "    if (parse_start() && peek() == '\\0') {",
                '        printf("Accepted\\n");',
                "    } else {",
                '        printf("Rejected\\n");',
                "    }",
                "    return 0;",
                "}",
                "",
            ]
        )
    return lines


def emit_parser_source(
    grammar: dict[str, list[list[str]]],
    local_names: list[str],
    include_runtime: bool,
    include_main: bool,
    source_input: dict[str, Any] | None = None,
) -> str:
    ordered = ["$start"] + sorted(name for name in grammar if name != "$start")
    lines = _emit_preamble(ordered, local_names, include_runtime)

    lines.extend(emit_function_definitions(grammar, local_names, include_main, source_input=source_input))
    return "\n".join(lines)


def emit_header(grammar: dict[str, list[list[str]]], local_names: list[str]) -> str:
    ordered = ["$start"] + sorted(name for name in grammar if name != "$start")
    lines = [
        "#ifndef PARSER_HELPERS_H",
        "#define PARSER_HELPERS_H",
        "#include <stddef.h>",
        "#include <stdio.h>",
        "extern const char *input;",
        "extern size_t pos;",
        "",
        "static char peek(void) __attribute__((no_profile_instrument_function));",
        "static int match_char(char c) __attribute__((no_profile_instrument_function));",
        "",
        "static char peek(void) {",
        "    while (input[pos]==' '||input[pos]=='\\t') pos++;",
        "    return input[pos];",
        "}",
        "",
        "static int match_char(char c) {",
        "    if (peek() == c) { pos++; return 1; }",
        "    return 0;",
        "}",
        "",
    ]
    for name in ordered:
        lines.append(f"int {c_func_name(name)}(void);")
    lines.extend(["#endif", ""])
    return "\n".join(lines)


def split_nonterminals(grammar: dict[str, list[list[str]]], file_count: int) -> dict[int, list[str]]:
    nonterms = sorted(name for name in grammar if name != "$start")
    parser_functions = 1 + len(nonterms)
    max_files = 2 if parser_functions == 1 else parser_functions + 1
    if file_count > max_files:
        raise ParserGenError("file_count exceeds available parser functions")
    if file_count <= 1:
        return {1: ["$start"] + nonterms}
    if file_count == 2:
        return {1: ["$start"] + nonterms}

    source_count = file_count - 1
    assignments: dict[int, list[str]] = {i: [] for i in range(1, source_count + 1)}
    assignments[1].append("$start")
    for idx, name in enumerate(nonterms):
        target = 2 + (idx % max(1, source_count - 1))
        assignments[target].append(name)
    return assignments


def _pad_parser_attributes(files: dict[str, str], source_input: dict[str, Any] | None) -> dict[str, str]:
    return files


def emit_parser_files(
    grammar: dict[str, list[list[str]]],
    file_count: int | None = None,
    source_input: dict[str, Any] | None = None,
) -> dict[str, str]:
    global _CURRENT_GRAMMAR
    _CURRENT_GRAMMAR = grammar
    if file_count is None:
        file_count = source_file_count(source_input)
    assignments = split_nonterminals(grammar, file_count)
    files: dict[str, str] = {}
    if file_count == 1:
        files["parser.c"] = emit_parser_source(
            grammar,
            assignments[1],
            include_runtime=True,
            include_main=True,
            source_input=source_input,
        )
        return _pad_parser_attributes(files, source_input)

    all_local = [name for names in assignments.values() for name in names]
    files["parser_helpers.h"] = emit_header(grammar, all_local)
    for index, local_names in assignments.items():
        filename = "parser.c" if index == 1 else f"parser_{index}.c"
        lines = ['#include "parser_helpers.h"', ""]
        if index == 1:
            lines.extend(["const char *input;", "size_t pos;", ""])
        lines.extend(
            emit_function_definitions(
                grammar,
                local_names,
                include_main=index == 1,
                source_input=source_input if index == 1 else None,
            )
        )
        files[filename] = "\n".join(lines)
    return _pad_parser_attributes(files, source_input)


def emit_makefile(files: dict[str, str], target: str = "parser.exe") -> str:
    c_files = sorted(name for name in files if name.endswith(".c"))
    if not c_files:
        raise ParserGenError("cannot emit Makefile without C source files")
    objects = [Path(name).with_suffix(".o").name for name in c_files]
    return "\n".join(
        [
            "CC ?= gcc",
            "CFLAGS ?= -O0",
            f"TARGET = {target}",
            "SRCS = " + " ".join(c_files),
            "OBJS = " + " ".join(objects),
            "",
            "all: $(TARGET)",
            "",
            "$(TARGET): $(OBJS)",
            "\t$(CC) $(CFLAGS) $(OBJS) -o $(TARGET)",
            "",
            "%.o: %.c parser_helpers.h",
            "\t$(CC) $(CFLAGS) -c $< -o $@",
            "",
            "parser.o: parser.c",
            "\t$(CC) $(CFLAGS) -c parser.c -o parser.o",
            "",
            "clean:",
            "\trm -f $(OBJS) $(TARGET)",
            "",
            ".PHONY: all clean",
            "",
        ]
    )


def emit_parser(grammar: dict[str, list[list[str]]]) -> str:
    return emit_parser_files(grammar, file_count=1)["parser.c"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a C parser from grammar JSON.")
    parser.add_argument("input", help="Input grammar JSON file, or '-' for stdin")
    parser.add_argument(
        "source_input",
        nargs="?",
        help="Original source input JSON file. Used for file_count and parser-size targets.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output C file or output directory. Multi-file parsers are written to a directory.",
    )
    parser.add_argument("--file-count", type=int, help="Total number of C parser files to emit.")
    args = parser.parse_args()

    try:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        grammar = validate_grammar(json.loads(text))
        source_input = None
        if args.source_input:
            source_input = json.loads(Path(args.source_input).read_text(encoding="utf-8"))
        files = emit_parser_files(grammar, file_count=args.file_count, source_input=source_input)
        if args.output:
            output = Path(args.output)
            if len(files) == 1 and output.suffix == ".c":
                output.write_text(files["parser.c"], encoding="utf-8")
            else:
                output.mkdir(parents=True, exist_ok=True)
                for filename, source in files.items():
                    (output / filename).write_text(source, encoding="utf-8")
                (output / "Makefile").write_text(emit_makefile(files), encoding="utf-8")
        else:
            print(files["parser.c"], end="")
    except (OSError, json.JSONDecodeError, ParserGenError) as exc:
        print(f"parser_gen.py: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
