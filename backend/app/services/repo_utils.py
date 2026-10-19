"""Shared repository-walking helpers."""

import os
from collections.abc import Iterator
from pathlib import Path

from app.config import get_settings

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv", "env", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".tox", ".idea", ".vscode", "site-packages",
}


def _excluded_workspace(repo_root: Path) -> Path | None:
    """CodeLiteracy's own workspace_dir (where cloned repos live), but only when it is
    nested *inside* the repo being scanned - e.g. someone connects CodeLiteracy's backend to
    itself. A repo that is itself a clone inside workspace_dir must not exclude itself."""
    workspace = Path(get_settings().workspace_dir).resolve()
    return workspace if repo_root == workspace or repo_root in workspace.parents else None


def iter_files(repo_path: str | Path, suffix: str | None = None) -> Iterator[Path]:
    """Yield files under repo_path, pruning junk directories instead of walking into them
    (node_modules / .venv can hold tens of thousands of files)."""
    root = Path(repo_path).resolve()
    workspace = _excluded_workspace(root)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS
            and not d.endswith(".egg-info")
            and not (workspace and (current / d).resolve() == workspace)
        )
        for name in sorted(filenames):
            if suffix is None or name.endswith(suffix):
                yield current / name
