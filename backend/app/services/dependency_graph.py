"""FR2: parse a (Python) repository and build a dependency graph of its files/modules,
based on `import` / `from ... import ...` statements that resolve to other files inside
the same repo. External-package imports are not part of the graph - only intra-repo
structure is.
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from app.services.repo_utils import iter_files


@dataclass
class ParsedModule:
    rel_path: str  # posix-style, relative to repo root
    dotted: str  # dotted module name, e.g. "app.services.github_service"
    is_package: bool  # True for __init__.py


@dataclass
class Graph:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)


def _iter_python_files(repo_path: Path):
    return iter_files(repo_path, suffix=".py")


def _to_dotted(rel_path: Path) -> tuple[str, bool]:
    is_package = rel_path.name == "__init__.py"
    parts = list(rel_path.with_suffix("").parts)
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def _discover_modules(repo_path: Path) -> list[ParsedModule]:
    modules = []
    for path in _iter_python_files(repo_path):
        rel = path.relative_to(repo_path)
        dotted, is_package = _to_dotted(rel)
        if not dotted:
            continue
        modules.append(ParsedModule(rel_path=rel.as_posix(), dotted=dotted, is_package=is_package))
    return modules


def _resolve(dotted: str, dotted_to_rel: dict[str, str]) -> str | None:
    """Match a dotted import target to a known in-repo module, trying progressively
    shorter prefixes (so `import pkg.sub.mod` still resolves if `pkg.sub` is the most
    specific thing we parsed)."""
    parts = dotted.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in dotted_to_rel:
            return dotted_to_rel[candidate]
        parts.pop()
    return None


def _package_of(module: ParsedModule) -> list[str]:
    parts = module.dotted.split(".")
    return parts if module.is_package else parts[:-1]


def _extract_edges(module: ParsedModule, tree: ast.AST, dotted_to_rel: dict[str, str]) -> set[str]:
    targets: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve(alias.name, dotted_to_rel)
                if resolved and resolved != module.rel_path:
                    targets.add(resolved)

        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                package_parts = _package_of(module)
                up = node.level - 1
                base_parts = package_parts[: len(package_parts) - up] if up <= len(package_parts) else []
                base = ".".join(base_parts)
                base = f"{base}.{node.module}" if base and node.module else (node.module or base)
            else:
                base = node.module

            candidates = [base] if base else []
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidates.append(f"{base}.{alias.name}" if base else alias.name)

            for cand in candidates:
                if not cand:
                    continue
                resolved = _resolve(cand, dotted_to_rel)
                if resolved and resolved != module.rel_path:
                    targets.add(resolved)

    return targets


def build_dependency_graph(repo_path: str) -> Graph:
    root = Path(repo_path).resolve()
    modules = _discover_modules(root)
    dotted_to_rel = {m.dotted: m.rel_path for m in modules}

    nx_graph = nx.DiGraph()
    for m in modules:
        nx_graph.add_node(
            m.rel_path,
            label=m.rel_path.rsplit("/", 1)[-1],
            kind="package" if m.is_package else "module",
        )

    for m in modules:
        source_path = root / m.rel_path
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for target in _extract_edges(m, tree, dotted_to_rel):
            nx_graph.add_edge(m.rel_path, target)

    graph = Graph()
    for node_id, attrs in nx_graph.nodes(data=True):
        graph.nodes.append({"id": node_id, "label": attrs["label"], "kind": attrs["kind"]})
    for source, target in nx_graph.edges():
        graph.edges.append({"source": source, "target": target})
    return graph
