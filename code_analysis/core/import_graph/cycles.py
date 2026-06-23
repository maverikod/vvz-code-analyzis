"""
Cycle detection over a dependency adjacency map (shared core utility).

Iterative Tarjan SCC: returns each cycle (SCC of size >= 2, plus self-loops) as
an ordered list of node ids. Pure; used by both ``analyze_tree`` cycles mode and
the comprehensive_analysis circular-import check so they cannot disagree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict, List, Set


def find_cycles(adjacency: Dict[str, Set[str]]) -> List[List[str]]:
    """Return cycles (SCCs of size >= 2, plus self-loops) via Tarjan's algorithm.

    Each cycle is an ordered list of node ids. Iterative to avoid recursion
    limits on large graphs.
    """
    index_counter = [0]
    stack: List[str] = []
    on_stack: Set[str] = set()
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    result: List[List[str]] = []
    nodes = sorted(adjacency.keys())

    for root in nodes:
        if root in indices:
            continue
        work: List[tuple[str, list[str]]] = [(root, sorted(adjacency.get(root, ())))]
        indices[root] = lowlink[root] = index_counter[0]
        index_counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, neighbors = work[-1]
            progressed = False
            while neighbors:
                w = neighbors.pop(0)
                if w not in indices:
                    indices[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, sorted(adjacency.get(w, ()))))
                    progressed = True
                    break
                if w in on_stack:
                    lowlink[node] = min(lowlink[node], indices[w])
            if progressed:
                continue
            if lowlink[node] == indices[node]:
                comp: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                self_loop = node in adjacency.get(node, set())
                if len(comp) >= 2 or self_loop:
                    result.append(list(reversed(comp)))
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return result
