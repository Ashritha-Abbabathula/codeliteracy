"""FR1: connect to a repo either by cloning it (a GitHub URL) or linking it directly
(an existing local folder)."""

import re
import shutil
import uuid
from pathlib import Path

from git import Actor, GitCommandError, InvalidGitRepositoryError, Repo

from app.config import get_settings


class RepoConnectionError(Exception):
    pass


SELF_SAMPLE_SOURCE = "sample:codeliteracy"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _looks_like_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@"))


def _repo_name_from_source(source: str) -> str:
    cleaned = source.rstrip("/").removesuffix(".git")
    return cleaned.rsplit("/", 1)[-1] or "repository"


def _with_auth(url: str, token: str) -> str:
    if not token or not url.startswith("https://") or "@" in url.split("//", 1)[1]:
        return url
    return url.replace("https://", f"https://{token}@", 1)


def create_self_snapshot() -> tuple[str, str]:
    """A fresh, disposable, git-initialized copy of CodeLiteracy's own backend, for the "explore
    CodeLiteracy itself" sample. Connecting the real project folder would let the AI assistant
    edit (and commit to) the very code that's running the app; a per-connection copy also means
    one session's edits never leak into the next, and the sample is always current."""
    source = _PROJECT_ROOT / "backend" / "app"
    if not source.is_dir():
        raise RepoConnectionError("The CodeLiteracy sample isn't available in this installation.")
    dest = Path(get_settings().workspace_dir).resolve() / f"codeliteracy-{uuid.uuid4().hex[:8]}"
    shutil.copytree(source, dest / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    readme = _PROJECT_ROOT / "README.md"
    if readme.is_file():
        shutil.copy(readme, dest / "README.md")
    repo = Repo.init(dest)
    # Not the files under .git itself: Repo.init has just created them, and git (rightly)
    # refuses to track its own metadata.
    repo.index.add([
        p.relative_to(dest).as_posix()
        for p in dest.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(dest).parts
    ])
    repo.index.commit("Snapshot of CodeLiteracy for exploration", author=_COMMIT_AUTHOR, committer=_COMMIT_AUTHOR)
    return "codeliteracy", str(dest)


def connect_repository(source: str) -> tuple[str, str]:
    """Returns (name, local_path). Clones GitHub URLs into the workspace dir; treats
    an existing local path as already-linked and uses it in place."""
    settings = get_settings()
    source = source.strip()

    if source == SELF_SAMPLE_SOURCE:
        return create_self_snapshot()

    if _looks_like_url(source):
        if not re.match(r"^(https://|git@)", source):
            raise RepoConnectionError(f"Unsupported repository source: {source}")

        name = _repo_name_from_source(source)
        dest = Path(settings.workspace_dir) / f"{name}-{uuid.uuid4().hex[:8]}"
        clone_url = _with_auth(source, settings.github_token)
        try:
            # GIT_TERMINAL_PROMPT=0: a private or mistyped URL must fail fast, not hang
            # the request waiting for credentials on a terminal nobody is watching.
            Repo.clone_from(
                clone_url,
                dest,
                depth=1,
                single_branch=True,
                env={"GIT_TERMINAL_PROMPT": "0"},
            )
        except GitCommandError as exc:
            shutil.rmtree(dest, ignore_errors=True)
            detail = str(exc)
            if settings.github_token:
                detail = detail.replace(settings.github_token, "***")  # never echo the token back
            raise RepoConnectionError(
                f"Could not clone '{source}'. Check the URL and, for private repos, "
                f"that GITHUB_TOKEN is set. ({detail.strip().splitlines()[-1] if detail.strip() else 'git error'})"
            ) from exc
        return name, str(dest)

    local_path = Path(source).expanduser().resolve()
    if not local_path.is_dir():
        raise RepoConnectionError(f"'{source}' is not a GitHub URL or an existing local folder.")
    return local_path.name, str(local_path)


_COMMIT_AUTHOR = Actor("CodeLiteracy", "codeliteracy@users.noreply.local")


def commit_changes(repo_path: str, message: str, paths: list[str]) -> str | None:
    """Commit exactly the files the assistant changed (never `git add -A`: a linked local
    repo may hold the user's own uncommitted work, which must not be swept into a commit
    labelled as an AI change). Returns the new commit's SHA, or None if the folder isn't a
    git repo or none of those files actually differ."""
    if not paths:
        return None
    try:
        repo = Repo(repo_path)
    except InvalidGitRepositoryError:
        return None

    root = Path(repo.working_tree_dir).resolve()
    repo_root = Path(repo_path).resolve()
    rel_to_git_root = []
    for p in paths:
        absolute = (repo_root / p).resolve()
        try:
            rel_to_git_root.append(absolute.relative_to(root).as_posix())
        except ValueError:
            continue

    changed = [
        p for p in rel_to_git_root
        if p in repo.untracked_files or any(d.a_path == p or d.b_path == p for d in repo.index.diff(None))
    ]
    if not changed:
        return None

    present = [p for p in changed if (root / p).exists()]
    gone = [p for p in changed if not (root / p).exists()]  # e.g. undoing a file the AI created
    if present:
        repo.index.add(present)
    if gone:
        repo.index.remove(gone)
    commit = repo.index.commit(message[:200], author=_COMMIT_AUTHOR, committer=_COMMIT_AUTHOR)
    return commit.hexsha
