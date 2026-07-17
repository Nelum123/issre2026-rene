#!/usr/bin/env python3
"""
Fixed MRD calculator for GCC CFG dumps.

What this fixes:
- The previous version collapsed every "goto-only" block as a compiler forwarder.
- That is wrong for source-level `break;` blocks. In the supplied project,
  run_gateway:bb16 is a real `break;` from `if (total > 100)`, so it must be
  counted with DR = 6.

Recommended GCC flags:
    -O0 -fdump-tree-cfg -fdump-tree-cfg-graph -fdump-ipa-cgraph

This script prefers textual .cfg dumps because they preserve GCC loop metadata
more clearly. If no .cfg files are present, it falls back to .cfg.dot files.
"""

from __future__ import annotations

import argparse
import glob
import heapq
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any


INF = 10**12
Node = Tuple[str, int]


@dataclass
class LoopInfo:
    id: int
    header: int
    latch: int = -1
    nodes: Set[int] = field(default_factory=set)


@dataclass
class FunctionCFG:
    name: str
    source_file: str
    raw_blocks: Dict[int, str]
    raw_succs: Dict[int, List[int]]
    raw_entry: Optional[int]
    loops: List[LoopInfo] = field(default_factory=list)

    ignored: Dict[int, str] = field(default_factory=dict)
    blocks: Dict[int, str] = field(default_factory=dict)
    succs: Dict[int, List[int]] = field(default_factory=dict)
    entry: Optional[int] = None
    decision: Dict[int, bool] = field(default_factory=dict)
    calls: Dict[int, List[str]] = field(default_factory=dict)


def clean_lines(body: str) -> List[str]:
    """Remove GCC-only labels/comments but keep real statements/gotos/ifs."""
    out: List[str] = []
    for line in body.splitlines():
        s = line.strip().strip("|").strip()
        if not s:
            continue
        if s.startswith("//"):
            continue
        # GCC text CFG labels and Graphviz labels:
        #   <bb 2>:
        #   {<bb 2>:
        if re.fullmatch(r"\{?\s*<bb\s+\d+>:", s):
            continue
        if re.fullmatch(r"<[^>]+>:", s):
            continue
        if s in {"{", "}"}:
            continue
        out.append(s)
    return out


def is_decision_block(body: str) -> bool:
    return bool(re.search(r"\bif\s*\(|\bswitch\s*\(", body))


def is_synthetic_return_only_sink(body: str) -> bool:
    lines = clean_lines(body)
    return len(lines) == 1 and bool(re.match(r"return\b", lines[0]))


def is_goto_only(body: str) -> bool:
    lines = clean_lines(body)
    return len(lines) == 1 and bool(re.match(r"goto\s+<bb\s+\d+>;", lines[0]))


def goto_target(body: str) -> Optional[int]:
    m = re.search(r"goto\s+<bb\s+(\d+)>;", body)
    return int(m.group(1)) if m else None


def parse_text_cfg(path: Path) -> Dict[str, FunctionCFG]:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = re.split(r"(?=;; Function\s+[A-Za-z_]\w*\s+\()", text)
    functions: Dict[str, FunctionCFG] = {}

    for section in sections:
        m = re.match(r";; Function\s+([A-Za-z_]\w*)\s+\(", section)
        if not m:
            continue

        fn_name = m.group(1)
        blocks: Dict[int, str] = {}
        succs: Dict[int, List[int]] = {}

        for bm in re.finditer(
            r"\n\s*<bb\s+(\d+)>\s*:(.*?)(?=\n\s*<bb\s+\d+>\s*:|\n}\s*\n|\Z)",
            section,
            re.S,
        ):
            bb = int(bm.group(1))
            body = bm.group(2).strip()
            blocks[bb] = body
            succs[bb] = []

        raw_succ_lines: Dict[int, List[int]] = {}
        for sm in re.finditer(r";;\s+(\d+)\s+succs\s+\{([^}]*)\}", section):
            src = int(sm.group(1))
            targets = [int(x) for x in sm.group(2).split()]
            raw_succ_lines[src] = targets
            if src in succs:
                succs[src] = [t for t in targets if t in blocks]

        entry_candidates = raw_succ_lines.get(0, [])
        entry = next((x for x in entry_candidates if x in blocks), min(blocks) if blocks else None)

        loops: List[LoopInfo] = []
        for lm in re.finditer(r";;\s+Loop\s+(\d+)\n(.*?)(?=\n;;\s+Loop|\n;;\s+\d+\s+succs|\Z)", section, re.S):
            loop_id = int(lm.group(1))
            body = lm.group(2)
            hm = re.search(r"header\s+(\d+),\s*latch\s+(-?\d+)", body)
            nm = re.search(r"nodes:\s*([0-9\s]+)", body)
            if hm and nm:
                loops.append(
                    LoopInfo(
                        id=loop_id,
                        header=int(hm.group(1)),
                        latch=int(hm.group(2)),
                        nodes=set(map(int, nm.group(1).split())),
                    )
                )

        functions[fn_name] = FunctionCFG(
            name=fn_name,
            source_file=path.name,
            raw_blocks=blocks,
            raw_succs=succs,
            raw_entry=entry,
            loops=loops,
        )

    return functions


def parse_cgraph_function_map(path: Path) -> Dict[int, str]:
    """
    Map GCC fn_N prefixes to function names.

    GCC versions differ here:
    - some cgraph dumps print route_action/0 for fn_0
    - others print route_action/1 for fn_0

    So we first collect all locally-defined functions. If any definition uses UID 0,
    the dump is treated as 0-based; otherwise it is treated as 1-based.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    defs: List[Tuple[int, str]] = []
    for m in re.finditer(r"^([A-Za-z_]\w*)/(\d+)\s+\(\1\)\n(.*?)(?=\n[A-Za-z_]\w*/\d+\s+\(|\n\n|\Z)", text, re.M | re.S):
        name = m.group(1)
        uid = int(m.group(2))
        details = m.group(3)
        if "Type: function definition" in details:
            defs.append((uid, name))

    if not defs:
        return {}

    zero_based = any(uid == 0 for uid, _name in defs)
    mapping: Dict[int, str] = {}
    for uid, name in defs:
        mapping[uid if zero_based else uid - 1] = name
    return mapping


def decode_dot_label(label: str) -> str:
    s = label
    s = s.replace("\\l\\\n", "\n")
    s = s.replace("\\l", "\n")
    s = s.replace("\\n", "\n")
    s = s.replace("\\<", "<").replace("\\>", ">")
    s = s.replace("\\ ", " ")
    s = s.replace('\\"', '"')
    # Drop remaining Graphviz escaping while keeping text readable.
    s = s.replace("\\", "")
    s = s.replace("|", "")
    return s.strip()


def parse_dot_cfg(path: Path, cgraph_map: Dict[int, str]) -> Dict[str, FunctionCFG]:
    text = path.read_text(encoding="utf-8", errors="replace")
    by_index_blocks: Dict[int, Dict[int, str]] = defaultdict(dict)
    by_index_succs: Dict[int, Dict[int, List[int]]] = defaultdict(lambda: defaultdict(list))
    by_index_entry: Dict[int, Optional[int]] = defaultdict(lambda: None)
    by_index_loops: Dict[int, List[LoopInfo]] = defaultdict(list)

    # Function names from valid subgraph labels are a fallback if no cgraph exists.
    label_map: Dict[int, str] = {}
    for sub in re.finditer(r'subgraph\s+"cluster_([A-Za-z_]\w*)"\s*\{(.*?)(?=\nsubgraph\s+"cluster_|\n}\s*\n}\s*$|\Z)', text, re.S):
        name = sub.group(1)
        body = sub.group(2)
        ids = [int(x) for x in re.findall(r"fn_(\d+)_basic_block_", body)]
        if ids:
            # Use the most common fn index in this cluster.
            idx = Counter(ids).most_common(1)[0][0]
            label_map[idx] = name

    node_re = re.compile(
        r"fn_(\d+)_basic_block_(\d+)\s*\[[^\]]*?label=\"(.*?)\"\];",
        re.S,
    )
    for nm in node_re.finditer(text):
        idx = int(nm.group(1))
        bb = int(nm.group(2))
        label = decode_dot_label(nm.group(3))
        if label in {"ENTRY", "EXIT"}:
            continue
        by_index_blocks[idx][bb] = label

    edge_re = re.compile(
        r"fn_(\d+)_basic_block_(\d+):s\s*->\s*fn_(\d+)_basic_block_(\d+):n\s*\[(.*?)\];",
        re.S,
    )
    for em in edge_re.finditer(text):
        src_idx, src_bb, dst_idx, dst_bb = map(int, em.group(1, 2, 3, 4))
        attrs = em.group(5)
        if src_idx != dst_idx:
            continue
        if "style=\"invis\"" in attrs:
            continue
        if src_bb == 0:
            if dst_bb not in (0, 1):
                by_index_entry[src_idx] = dst_bb
            continue
        if dst_bb == 1:
            continue
        by_index_succs[src_idx][src_bb].append(dst_bb)

    # Best-effort loop extraction from dot loop clusters.
    # Do this line-by-line because node labels contain braces, so a simple
    # regex ending at the first "}" truncates the cluster.
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m_loop = re.search(r"subgraph\s+cluster_(\d+)_(\d+)\s*\{", lines[i])
        if not m_loop:
            i += 1
            continue

        idx = int(m_loop.group(1))
        lid = int(m_loop.group(2))
        body_lines: List[str] = []
        i += 1
        while i < len(lines) and lines[i].strip() != "}":
            body_lines.append(lines[i])
            i += 1

        body = "\n".join(body_lines)
        nodes = [int(x) for x in re.findall(rf"fn_{idx}_basic_block_(\d+)", body)]
        if nodes:
            by_index_loops[idx].append(LoopInfo(id=lid, header=nodes[0], nodes=set(nodes)))
        i += 1

    functions: Dict[str, FunctionCFG] = {}
    all_indices = set(by_index_blocks) | set(by_index_succs) | set(by_index_entry)
    for idx in sorted(all_indices):
        fn_name = label_map.get(idx) or cgraph_map.get(idx) or f"fn_{idx}"
        blocks = by_index_blocks.get(idx, {})
        succs = {bb: [t for t in by_index_succs[idx].get(bb, []) if t in blocks] for bb in blocks}
        entry = by_index_entry.get(idx)
        if entry not in blocks:
            entry = min(blocks) if blocks else None
        functions[fn_name] = FunctionCFG(
            name=fn_name,
            source_file=path.name,
            raw_blocks=blocks,
            raw_succs=succs,
            raw_entry=entry,
            loops=by_index_loops.get(idx, []),
        )

    return functions


def should_preserve_goto_as_source_break(fd: FunctionCFG, bb: int, preds: Dict[int, List[int]]) -> bool:
    """Preserve goto-only source-level break blocks; collapse compiler forwarders."""
    if not is_goto_only(fd.raw_blocks[bb]):
        return False
    if len(fd.raw_succs.get(bb, [])) != 1:
        return False

    target = fd.raw_succs[bb][0]

    # A real break generated by GCC commonly appears as:
    #   inner decision inside a loop -> goto-only block outside the loop -> after-loop block
    # The predecessor is inside the loop but is not the loop header itself.
    for pred in preds.get(bb, []):
        if not is_decision_block(fd.raw_blocks.get(pred, "")):
            continue
        for loop in fd.loops:
            if loop.id == 0:
                continue
            if (
                pred in loop.nodes
                and pred != loop.header
                and bb not in loop.nodes
                and target not in loop.nodes
            ):
                return True
    return False


def normalise_function(fd: FunctionCFG) -> None:
    preds: Dict[int, List[int]] = defaultdict(list)
    for src, targets in fd.raw_succs.items():
        for target in targets:
            preds[target].append(src)

    ignored: Dict[int, str] = {}

    loop_headers = {lp.header for lp in fd.loops if lp.id != 0}
    for_init_headers: Set[int] = set()

    # Compiler-created pre-loop setup blocks, e.g.
    #
    #   total = 0;
    #   i = 0;
    #   goto <bb 7>;
    #
    # GCC often places function-local initialisation and the first for/while-loop
    # initialiser in a separate basic block before the loop condition. For the
    # source-level MRD definition used here, that scaffolding is not a real
    # decision/reachability block; the loop condition is the source-level block.
    #
    # The earlier script only handled exactly two-line blocks such as
    # "i = 0; goto <header>;". That missed blocks like
    # "score = 0; j = 0; goto <header>;" and caused init blocks to be counted.
    assignment_re = re.compile(r"^[A-Za-z_]\w*(?:\.[0-9]+)?\s*=\s*.+;$")
    for bb, body in fd.raw_blocks.items():
        lines = clean_lines(body)
        if len(lines) < 2:
            continue
        if not re.match(r"goto\s+<bb\s+\d+>;", lines[-1]):
            continue
        target = goto_target(lines[-1])
        if target not in loop_headers:
            continue
        if is_decision_block(body):
            continue
        # Do not erase blocks that contain calls, returns, or non-assignment
        # source statements. Calls should remain as real blocks so their callees
        # are reachable in the interprocedural graph.
        setup_lines = lines[:-1]
        if not setup_lines:
            continue
        if any("(" in line and ")" in line for line in setup_lines):
            continue
        if all(assignment_re.match(line) for line in setup_lines):
            ignored[bb] = "compiler_loop_setup"
            for_init_headers.add(target)

    # Synthetic return sink blocks, e.g. a GCC temp has already been assigned earlier.
    for bb, body in fd.raw_blocks.items():
        if bb not in ignored and is_synthetic_return_only_sink(body):
            ignored[bb] = "synthetic_return_only_sink"

    # Compiler-created for-loop increment blocks. Only ignore increments for loops that
    # also had an ignored for-loop init; this avoids incorrectly ignoring real while-body
    # statements such as "value = value + 5;".
    for bb, body in fd.raw_blocks.items():
        if bb in ignored:
            continue
        lines = clean_lines(body)
        if len(lines) == 1 and re.match(r"([A-Za-z_]\w*)\s*=\s*\1\s*[+\-]\s*[^;]+;", lines[0]):
            if any(t in for_init_headers for t in fd.raw_succs.get(bb, [])):
                ignored[bb] = "compiler_for_loop_increment"

    # Empty forwarder gotos are compiler scaffolding, except real source-level break blocks.
    for bb, body in fd.raw_blocks.items():
        if bb in ignored:
            continue
        if is_goto_only(body) and not should_preserve_goto_as_source_break(fd, bb, preds):
            ignored[bb] = "empty_forwarder_goto"

    def resolve(bb: int, seen: Optional[Set[int]] = None) -> List[int]:
        if seen is None:
            seen = set()
        if bb in seen:
            return []
        seen.add(bb)

        if bb not in ignored:
            return [bb]

        out: List[int] = []
        for target in fd.raw_succs.get(bb, []):
            out.extend(resolve(target, set(seen)))

        result: List[int] = []
        for x in out:
            if x not in result:
                result.append(x)
        return result

    fd.ignored = ignored
    fd.blocks = {bb: body for bb, body in fd.raw_blocks.items() if bb not in ignored}
    fd.succs = {bb: [] for bb in fd.blocks}

    for bb in fd.blocks:
        norm_targets: List[int] = []
        for target in fd.raw_succs.get(bb, []):
            for resolved in resolve(target):
                if resolved in fd.blocks and resolved not in norm_targets:
                    norm_targets.append(resolved)
        fd.succs[bb] = norm_targets

    entry_resolved = resolve(fd.raw_entry) if fd.raw_entry is not None else []
    fd.entry = entry_resolved[0] if entry_resolved else (min(fd.blocks) if fd.blocks else None)
    fd.decision = {bb: is_decision_block(body) for bb, body in fd.blocks.items()}


def find_functions(dump_dir: Path) -> Tuple[Dict[str, FunctionCFG], str]:
    # Prefer textual .cfg dumps. They are generated alongside .cfg.dot by
    # -fdump-tree-cfg-graph and carry clearer loop metadata.
    cfg_files = sorted(
        p for p in dump_dir.glob("*.cfg")
        if not p.name.endswith(".cfg.dot")
    )
    functions: Dict[str, FunctionCFG] = {}

    if cfg_files:
        for path in cfg_files:
            functions.update(parse_text_cfg(path))
        return functions, "textual .cfg"

    dot_files = sorted(dump_dir.glob("*.cfg.dot"))
    if not dot_files:
        raise FileNotFoundError(f"No .cfg or .cfg.dot files found in {dump_dir}")

    cgraph_maps: Dict[str, Dict[int, str]] = {}
    for cgraph in dump_dir.glob("*.cgraph"):
        # Match "foo.c.000i.cgraph" or "bin-foo.c.000i.cgraph" with "foo.c.*.cfg.dot".
        base = re.sub(r"\.\d+i\.cgraph$", "", cgraph.name)
        cgraph_maps[base] = parse_cgraph_function_map(cgraph)

    for dot in dot_files:
        base = re.sub(r"\.\d+t\.cfg\.dot$", "", dot.name)
        cmap = cgraph_maps.get(base, {})
        functions.update(parse_dot_cfg(dot, cmap))

    return functions, "Graphviz .cfg.dot"


def attach_calls(functions: Dict[str, FunctionCFG]) -> None:
    known = set(functions)
    for fn, fd in functions.items():
        fd.calls = {}
        for bb, body in fd.blocks.items():
            callees = []
            for name in known:
                if name != fn and re.search(r"\b" + re.escape(name) + r"\s*\(", body):
                    callees.append(name)
            fd.calls[bb] = sorted(callees)


def compute_mrd(functions: Dict[str, FunctionCFG], entry_function: str) -> Dict[str, Any]:
    if entry_function not in functions:
        raise KeyError(f"Entry function {entry_function!r} not found. Available: {sorted(functions)}")

    for fd in functions.values():
        normalise_function(fd)
    attach_calls(functions)

    adjacency: Dict[Node, List[Tuple[Node, int, str]]] = defaultdict(list)
    for fn, fd in functions.items():
        for bb in fd.blocks:
            node = (fn, bb)
            edge_cost = 1 if fd.decision[bb] else 0
            reason = "branch-decision" if edge_cost else "straight-line"

            for target in fd.succs.get(bb, []):
                adjacency[node].append(((fn, target), edge_cost, reason))

            for callee in fd.calls.get(bb, []):
                callee_entry = functions[callee].entry
                if callee_entry is not None:
                    adjacency[node].append(((callee, callee_entry), 0, f"call:{callee}"))

    start_bb = functions[entry_function].entry
    if start_bb is None:
        raise ValueError(f"Entry function {entry_function!r} has no usable entry block")
    start: Node = (entry_function, start_bb)

    dist: Dict[Node, int] = {start: 0}
    pq: List[Tuple[int, Node]] = [(0, start)]

    while pq:
        d, node = heapq.heappop(pq)
        if d != dist[node]:
            continue
        for nxt, cost, _reason in adjacency.get(node, []):
            nd = d + cost
            if nd < dist.get(nxt, INF):
                dist[nxt] = nd
                heapq.heappush(pq, (nd, nxt))

    functions_out: Dict[str, Any] = {}
    total_sum = 0
    total_blocks = 0
    hist = Counter()
    inter_edges = []

    for src, edges in sorted(adjacency.items()):
        if src not in dist:
            continue
        for dst, cost, reason in edges:
            if dst in dist and dist[dst] == dist[src] + cost:
                inter_edges.append(
                    {
                        "from": f"{src[0]}:bb{src[1]}",
                        "to": f"{dst[0]}:bb{dst[1]}",
                        "cost": cost,
                        "reason": reason,
                    }
                )

    for fn in sorted(functions):
        fd = functions[fn]
        blocks_out: Dict[str, Any] = {}
        fn_sum = 0
        fn_count = 0

        for bb in sorted(fd.blocks):
            node = (fn, bb)
            reachable = node in dist
            counted = reachable and node != start
            dr = dist[node] if reachable else None

            if counted:
                fn_sum += int(dr)
                fn_count += 1
                total_sum += int(dr)
                total_blocks += 1
                hist[int(dr)] += 1

            blocks_out[f"bb{bb}"] = {
                "reachable": reachable,
                "DR": dr,
                "counted_in_MRD": counted,
                "is_project_entry_block": node == start,
                "is_function_entry_block": bb == fd.entry,
                "is_decision_block": fd.decision.get(bb, False),
                "successors_after_normalisation": [f"bb{x}" for x in fd.succs.get(bb, [])],
                "calls": fd.calls.get(bb, []),
                "text": fd.blocks[bb],
            }

        functions_out[fn] = {
            "source_file": fd.source_file,
            "entry_block": f"bb{fd.entry}" if fd.entry is not None else None,
            "raw_gcc_blocks": len(fd.raw_blocks),
            "source_level_blocks_after_normalisation": len(fd.blocks),
            "reachable_source_level_blocks": sum(1 for bb in fd.blocks if (fn, bb) in dist),
            "counted_blocks": fn_count,
            "sum_DR": fn_sum,
            "MRD_contribution_average": fn_sum / fn_count if fn_count else 0.0,
            "ignored_blocks": {f"bb{k}": v for k, v in sorted(fd.ignored.items())},
            "blocks": blocks_out,
        }

    return {
        "MRD": total_sum / total_blocks if total_blocks else 0.0,
        "blocks": total_blocks,
        "conditional_statements": sum(
            1
            for fn, fd in functions.items()
            for bb in fd.blocks
            if (fn, bb) in dist and fd.decision.get(bb, False)
        ),
        "sum_reachable_depth": total_sum,
        "reachable_depth_distribution": [
            {"depth": depth, "count": hist[depth]}
            for depth in sorted(hist)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate MRD from GCC CFG dumps.")
    parser.add_argument("dump_dir", nargs="?", default=".", help="Directory containing .cfg/.cfg.dot/.cgraph dumps")
    parser.add_argument("--entry", default="main", help="Entry function name, default: main")
    parser.add_argument("--json-out", default="mrd_output.json", help="JSON output filename")
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir).resolve()
    functions, _source_kind = find_functions(dump_dir)
    result = compute_mrd(functions, args.entry)

    json_path = dump_dir / args.json_out
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    print(f"Wrote: {json_path}")


if __name__ == "__main__":
    main()
