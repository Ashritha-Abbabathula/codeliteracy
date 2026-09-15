"""FR1: connect to a repo either by cloning it (a GitHub URL) or linking it directly
(an existing local folder)."""

import re
import uuid
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo

from app.config import get_settings


class RepoConnectionError(Exception):
    pass


def _looks_like_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@"))


def _repo_name_from_source(source: str) -> str:
    cleaned = source.rstrip("/").removesuffix(".git")
    return cleaned.rsplit("/", 1)[-1] or "repository"


def _with_auth(url: str, token: str) -> str:
    if not token or not url.startswith("https://") or "@" in url.split("//", 1)[1]:
        return url
    return url.replace("https://", f"https://{token}@", 1)


def connect_repository(source: str) -> tuple[str, str]:
    """Returns (name, local_path). Clones GitHub URLs into the workspace dir; treats
    an existing local path as already-linked and uses it in place."""
    settings = get_settings()

    if _looks_like_url(source):
        if not re.match(r"^(https://|git@)", source):
            raise RepoConnectionError(f"Unsupported repository source: {source}")

        name = _repo_name_from_source(source)
        dest = Path(settings.workspace_dir) / f"{name}-{uuid.uuid4().hex[:8]}"
        clone_url = _with_auth(source, settings.github_token)
        try:
            Repo.clone_from(clone_url, dest, depth=1)
        except GitCommandError as exc:
            raise RepoConnectionError(
                f"Could not clone '{source}'. Check the URL and, for private repos, "
                "that GITHUB_TOKEN is set. ({exc})"
            ) from exc
        return name, str(dest)

    local_path = Path(source).expanduser().resolve()
    if not local_path.is_dir():
        raise RepoConnectionError(f"'{source}' is not a GitHub URL or an existing local folder.")
    return local_path.name, str(local_path)


def commit_changes(repo_path: str, message: str) -> str | None:
    """FR6 (git tracking of assistant changes). Returns the new commit's SHA, or None
    if the folder isn't a git repo, or nothing actually changed."""
    try:
        repo = Repo(repo_path)
    except InvalidGitRepositoryError:
        return None
    if not repo.is_dirty(untracked_files=True):
        return None
    repo.git.add(A=True)
    commit = repo.index.commit(message)
    return commit.hexsha
