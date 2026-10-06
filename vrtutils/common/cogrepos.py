"""Repair Downloader commit records after a cog repo's history was rewritten.

Red's Downloader stores the commit each installed module came from. When it
checks for updates it only diffs modules whose stored commit is an ancestor of
the repo's HEAD (``_available_updates``); anything else is skipped without a
word. After a force-push, every installed module from that repo points at a
commit that is no longer in HEAD's history, so ``[p]cog update`` reports
"up to date" forever.

These helpers find a commit in HEAD's history to record instead:

1. The newest HEAD commit where the module folder's tree hash equals the tree
   at the stored commit (same code, new SHA). Red then diffs from there.
2. If no such tree exists (the code really changed), a HEAD commit where the
   module exists and differs from HEAD, preferring the newest one authored at
   or before the stored commit, then the merge-base, then the newest commit
   that differs from HEAD. Red then sees the module as modified and
   reinstalls it from HEAD on the next ``[p]cog update``.

The git helpers are synchronous (run them in a thread); the scan/apply
functions talk to the running Downloader through ``DownloaderAPI``.
"""

import asyncio
import os
import subprocess
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

GIT_TIMEOUT = 120

# How the replacement commit was picked
IDENTICAL = "identical tree"
BY_DATE = "code changed, by date"
MERGE_BASE = "code changed, merge-base"
LAST_DIFFERENT = "code changed, last differing commit"


class GitError(Exception):
    pass


def _git_env() -> dict:
    # Same idea as Red's Repo._run: never prompt, plain English output
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_TRACE"] = "0"
    env.pop("GIT_ASKPASS", None)
    env.pop("SSH_ASKPASS", None)
    env["LC_ALL"] = "C"
    env["LANGUAGE"] = "C"
    env["TERM"] = "dumb"
    return env


def git(path: t.Union[str, Path], *args: str, stdin: str = None, ok: t.Tuple[int, ...] = (0,)):
    proc = subprocess.run(
        ["git", "-C", str(path), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=_git_env(),
        timeout=GIT_TIMEOUT,
    )
    if proc.returncode not in ok:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc


def commit_exists(path: t.Union[str, Path], rev: str) -> bool:
    return git(path, "cat-file", "-e", f"{rev}^{{commit}}", ok=(0, 1, 128)).returncode == 0


def batch_check(path: t.Union[str, Path], specs: t.List[str]) -> t.List[t.Tuple[t.Optional[str], t.Optional[str]]]:
    """Resolve many `<rev>:<path>` specs in one process. Returns (sha, type) or (None, None) per spec."""
    if not specs:
        return []
    out = git(path, "cat-file", "--batch-check", stdin="\n".join(specs) + "\n").stdout.splitlines()
    results = []
    for line in out:
        parts = line.split()
        if len(parts) == 3 and parts[1] in ("tree", "blob", "commit", "tag"):
            results.append((parts[0], parts[1]))
        else:
            results.append((None, None))
    if len(results) != len(specs):
        raise GitError(f"cat-file --batch-check returned {len(results)} lines for {len(specs)} specs")
    return results


def head_history(path: t.Union[str, Path], head: str = "HEAD") -> t.List[t.Tuple[str, int]]:
    """Commits reachable from head, newest first, with their author timestamps."""
    out = git(path, "-c", "log.showSignature=false", "log", "--format=%H %at", head).stdout
    history = []
    for line in out.splitlines():
        sha, _, ts = line.partition(" ")
        history.append((sha, int(ts or 0)))
    return history


@dataclass
class Replacement:
    commit: t.Optional[str]  # None means no safe replacement, skip
    method: str


def find_replacement(path: t.Union[str, Path], old_commit: str, module: str, head: str = "HEAD") -> Replacement:
    """Pick the commit to record for `module` in place of `old_commit`, which is not in head's history."""
    if not commit_exists(path, old_commit):
        # The date of a missing object is unknowable from the clone
        return Replacement(None, "recorded commit is gone from the clone")

    history = head_history(path, head)
    if not history:
        return Replacement(None, "repo HEAD has no history")
    head_sha = history[0][0]

    specs = [f"{old_commit}:{module}"]
    for sha, _ in history:
        specs.append(f"{sha}:{module}")
        specs.append(f"{sha}:{module}/__init__.py")
    resolved = batch_check(path, specs)
    old_tree = resolved[0][0] if resolved[0][1] == "tree" else None
    trees: t.Dict[str, t.Optional[str]] = {}
    has_init: t.Dict[str, bool] = {}
    for i, (sha, _) in enumerate(history):
        tree_sha, tree_type = resolved[1 + i * 2]
        trees[sha] = tree_sha if tree_type == "tree" else None
        has_init[sha] = resolved[2 + i * 2][1] == "blob"

    # 1. Same code under a new SHA
    if old_tree:
        for sha, _ in history:
            if trees[sha] == old_tree:
                return Replacement(sha, IDENTICAL)

    # 2. Code changed. Red's get_modified_modules only reports modules that exist at the
    # recorded commit and differ from HEAD; anything else just gets its commit bumped
    # to HEAD without a reinstall. So a usable commit has the package and a different tree.
    head_tree = trees[head_sha]

    def usable(sha: str) -> bool:
        return trees.get(sha) is not None and has_init.get(sha, False) and trees[sha] != head_tree

    old_ts = int(git(path, "log", "-1", "--format=%at", old_commit).stdout.strip() or 0)
    best = None
    for idx, (sha, ts) in enumerate(history):
        if ts <= old_ts and usable(sha):
            # Newest author date wins, ties go to the newer commit in log order
            if best is None or ts > best[0]:
                best = (ts, idx, sha)
    if best:
        return Replacement(best[2], BY_DATE)

    mb = git(path, "merge-base", old_commit, head_sha, ok=(0, 1)).stdout.strip()
    if mb and usable(mb):
        return Replacement(mb, MERGE_BASE)

    for sha, _ in history:
        if usable(sha):
            return Replacement(sha, LAST_DIFFERENT)

    return Replacement(None, "no commit in HEAD history differs from HEAD for this module, reinstall it instead")


class DownloaderAPI:
    """The bits of Downloader we need, wherever this Red version keeps them."""

    def __init__(self, installed_cogs, installed_libraries, save_to_installed, source: str):
        self.installed_cogs = installed_cogs
        self.installed_libraries = installed_libraries
        self.save_to_installed = save_to_installed
        self.source = source

    @classmethod
    def from_cog(cls, cog: t.Any) -> "DownloaderAPI":
        """Build from the loaded Downloader cog.

        Red <= 3.5.24 keeps the state on the cog. Newer Red (3.5.25.dev7+) moved it to
        module-level functions in redbot.core._downloader sharing the same Config.
        """
        try:
            from redbot.core import _downloader as core  # type: ignore
        except ImportError:
            core = None

        names = ("installed_cogs", "installed_libraries", "_save_to_installed")
        if core is not None and hasattr(core, "_save_to_installed"):
            source, label = core, "redbot.core._downloader"
        else:
            source, label = cog, "Downloader cog"
        found = {name: getattr(source, name, None) for name in names}
        missing = [name for name, value in found.items() if value is None]
        if missing:
            raise RuntimeError(
                f"This Red version's Downloader is missing {', '.join(missing)} on {label}; "
                "fixcogrepos needs updating for it."
            )
        return cls(
            found["installed_cogs"],
            found["installed_libraries"],
            found["_save_to_installed"],
            label,
        )


@dataclass
class Fix:
    module: t.Any  # InstalledModule
    old_commit: str
    new_commit: str
    method: str


@dataclass
class RepoReport:
    name: str
    head: str = ""
    fixes: t.List[Fix] = field(default_factory=list)
    skipped: t.List[str] = field(default_factory=list)  # "module: reason"
    error: str = ""


@dataclass
class ScanResult:
    repos: t.Dict[str, RepoReport] = field(default_factory=dict)
    pinned: t.List[str] = field(default_factory=list)
    no_repo: t.List[str] = field(default_factory=list)
    red_handles: t.List[str] = field(default_factory=list)  # UnknownRevision or empty commit
    checked: int = 0

    @property
    def fixes(self) -> t.List[Fix]:
        return [fix for report in self.repos.values() for fix in report.fixes]


async def _update_repo(repo: t.Any) -> None:
    """Update the clone the way `[p]cog update` does (hard reset + pull --ff-only).

    Right after a force-push the first pull fails: the reset lands on the stale
    origin ref and the rewritten branch is not a fast-forward of it. That pull
    still fetched the new ref, so one retry resets onto it and succeeds.
    """
    try:
        await repo.update()
    except Exception:
        await repo.update()


def _lock(repo: t.Any) -> asyncio.Lock:
    # Hold Red's per-repo git lock so a concurrent cog update cannot check out mid-walk
    lock = getattr(repo, "_repo_lock", None)
    return lock if isinstance(lock, asyncio.Lock) else asyncio.Lock()


async def scan(api: DownloaderAPI, update_repos: bool = True) -> ScanResult:
    result = ScanResult()
    modules = tuple(await api.installed_cogs()) + tuple(await api.installed_libraries())

    by_repo: t.Dict[str, t.List[t.Any]] = {}
    for module in modules:
        if getattr(module, "pinned", False):
            result.pinned.append(module.name)
            continue
        if module.repo is None:
            result.no_repo.append(f"{module.name} ({getattr(module, '_json_repo_name', '') or module.repo_name})")
            continue
        if not module.commit:
            # Red marks these for update itself
            result.red_handles.append(module.name)
            continue
        by_repo.setdefault(module.repo.name, []).append(module)

    for repo_name, repo_modules in by_repo.items():
        repo = repo_modules[0].repo
        report = result.repos.setdefault(repo_name, RepoReport(repo_name))
        folder = Path(getattr(repo, "folder_path", ""))
        if not (folder / ".git").exists():
            report.error = f"no git clone at {folder}"
            continue
        if update_repos:
            try:
                await _update_repo(repo)
            except Exception as e:
                report.error = f"repo update failed: {e}"
                continue
        report.head = repo.commit
        for module in repo_modules:
            result.checked += 1
            if module.commit == repo.commit:
                continue
            try:
                is_ancestor = await repo.is_ancestor(module.commit, repo.commit)
            except Exception as e:
                if type(e).__name__ == "UnknownRevision":
                    # Red reinstalls from the last occurrence in this case, not stuck
                    result.red_handles.append(module.name)
                else:
                    report.skipped.append(f"{module.name}: ancestry check failed: {e}")
                continue
            if is_ancestor:
                continue
            try:
                async with _lock(repo):
                    found = await asyncio.to_thread(find_replacement, folder, module.commit, module.name, repo.commit)
            except Exception as e:
                report.skipped.append(f"{module.name}: {e}")
                continue
            if found.commit is None:
                report.skipped.append(f"{module.name}: {found.method}")
                continue
            report.fixes.append(Fix(module, module.commit, found.commit, found.method))

    return result


async def apply(api: DownloaderAPI, fixes: t.List[Fix]) -> t.Dict[str, str]:
    """Record the new commits, then read them back. Returns {module name: stored commit}."""
    for fix in fixes:
        fix.module.commit = fix.new_commit
    await api.save_to_installed([fix.module for fix in fixes])
    stored = tuple(await api.installed_cogs()) + tuple(await api.installed_libraries())
    wanted = {(fix.module.repo.name, fix.module.name) for fix in fixes}
    return {m.name: m.commit for m in stored if m.repo is not None and (m.repo.name, m.name) in wanted}
