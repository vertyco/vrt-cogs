"""Tests for vrtutils.common.cogrepos (the [p]fixcogrepos logic).

The pure git tests need only git. The integration tests drive Red's real
Downloader Repo / InstalledModule / _available_updates and skip without redbot.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Load the module by path so the test doesn't import the whole cog package
_SPEC = importlib.util.spec_from_file_location(
    "cogrepos", Path(__file__).resolve().parents[1] / "common" / "cogrepos.py"
)
cogrepos = importlib.util.module_from_spec(_SPEC)
sys.modules["cogrepos"] = cogrepos
_SPEC.loader.exec_module(cogrepos)


def run(path, *args, env=None, stdin=None):
    full_env = os.environ.copy()
    full_env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    full_env.update(env or {})
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True, env=full_env, input=stdin
    ).stdout.strip()


def write_module(repo: Path, name: str, body: str):
    folder = repo / name
    folder.mkdir(exist_ok=True)
    (folder / "__init__.py").write_text(body)
    (folder / "info.json").write_text(json.dumps({"name": name, "type": "COG"}))


def commit(repo: Path, msg: str, date: int) -> str:
    stamp = f"@{date} +0000"
    run(repo, "add", "-A")
    run(repo, "commit", "-q", "-m", msg, env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    return run(repo, "rev-parse", "HEAD")


def rewrite(repo: Path, commits, committer_date: int) -> list:
    """Replay the given commits' trees onto a fresh root: same trees, new SHAs.

    Keeps author dates (like rebase / filter-repo do), changes committer dates and messages.
    Returns the new SHAs in the same order.
    """
    new = []
    parent = None
    for sha in commits:
        tree = run(repo, "rev-parse", f"{sha}^{{tree}}")
        author_date = run(repo, "log", "-1", "--format=%at", sha)
        args = ["commit-tree", tree, "-m", f"rewritten {sha[:7]}"]
        if parent:
            args += ["-p", parent]
        env = {"GIT_AUTHOR_DATE": f"@{author_date} +0000", "GIT_COMMITTER_DATE": f"@{committer_date} +0000"}
        parent = run(repo, *args, env=env)
        new.append(parent)
    return new


@pytest.fixture
def history(tmp_path):
    """Old history c1..c4, rewritten as n1..n3 (c4 dropped, so its cogA tree exists nowhere new)."""
    repo = tmp_path / "work"
    repo.mkdir()
    run(repo, "init", "-q", "-b", "main")
    write_module(repo, "cogA", "v1")
    write_module(repo, "cogB", "v1")
    c1 = commit(repo, "c1", 1_000)
    write_module(repo, "cogB", "v2")
    c2 = commit(repo, "c2", 2_000)
    write_module(repo, "cogA", "v3")
    c3 = commit(repo, "c3", 3_000)
    # c4 only on the old history: cogA changed to something the rewrite never has
    write_module(repo, "cogA", "old-only")
    c4 = commit(repo, "c4", 4_000)
    n1, n2, n3 = rewrite(repo, [c1, c2, c3], committer_date=9_000)
    # move main to the rewritten history; old objects stay in the object store
    run(repo, "update-ref", "refs/heads/main", n3)
    run(repo, "reset", "-q", "--hard", n3)
    return SimpleNamespace(repo=repo, c=[c1, c2, c3, c4], n=[n1, n2, n3])


def test_old_commits_are_not_ancestors(history):
    for old in history.c:
        rc = subprocess.run(["git", "-C", str(history.repo), "merge-base", "--is-ancestor", old, "HEAD"]).returncode
        assert rc == 1


def test_identical_tree_picks_newest_matching_commit(history):
    # cogA at c2 is v1, unchanged in n1 and n2; n3 changes it. Newest identical is n2.
    found = cogrepos.find_replacement(history.repo, history.c[1], "cogA")
    assert found == cogrepos.Replacement(history.n[1], cogrepos.IDENTICAL)
    # cogB at c2 is v2, identical through n3
    found = cogrepos.find_replacement(history.repo, history.c[1], "cogB")
    assert found == cogrepos.Replacement(history.n[2], cogrepos.IDENTICAL)
    # cogA at c1 is the same v1 tree, so also n2
    assert cogrepos.find_replacement(history.repo, history.c[0], "cogA").commit == history.n[1]


def test_changed_code_falls_back_by_author_date(history):
    # cogA at c4 ("old-only") exists nowhere in the new history. Newest commit authored at or
    # before c4 (4000) whose cogA differs from HEAD's is n2 (2000); n3 has HEAD's tree.
    found = cogrepos.find_replacement(history.repo, history.c[3], "cogA")
    assert found == cogrepos.Replacement(history.n[1], cogrepos.BY_DATE)


def test_changed_code_without_dated_candidate_uses_last_differing(history):
    # Re-author the new history after c4 so no commit is dated at or before it; the
    # histories are disjoint so there is no merge-base either.
    repo = history.repo
    parent = None
    shifted = []
    for sha in history.n:
        tree = run(repo, "rev-parse", f"{sha}^{{tree}}")
        args = ["commit-tree", tree, "-m", "late"] + (["-p", parent] if parent else [])
        parent = run(repo, *args, env={"GIT_AUTHOR_DATE": "@50000 +0000", "GIT_COMMITTER_DATE": "@50000 +0000"})
        shifted.append(parent)
    run(repo, "reset", "-q", "--hard", shifted[-1])
    # cogA is v1 in shifted[0] and shifted[1], v3 at HEAD: newest differing is shifted[1]
    found = cogrepos.find_replacement(repo, history.c[3], "cogA")
    assert found == cogrepos.Replacement(shifted[1], cogrepos.LAST_DIFFERENT)


def test_merge_base_used_for_partial_rewrite(tmp_path):
    # base -> dropped (force-pushed away), base -> v2 (new HEAD). base is authored after
    # the dropped commit so the by-date rule finds nothing and the merge-base is used.
    repo = tmp_path / "work"
    repo.mkdir()
    run(repo, "init", "-q", "-b", "main")
    write_module(repo, "cogA", "v1")
    base = commit(repo, "base", 6_000)
    write_module(repo, "cogA", "dropped")
    dropped = commit(repo, "dropped", 5_000)
    run(repo, "reset", "-q", "--hard", base)
    write_module(repo, "cogA", "v2")
    commit(repo, "v2", 7_000)
    found = cogrepos.find_replacement(repo, dropped, "cogA")
    assert found == cogrepos.Replacement(base, cogrepos.MERGE_BASE)


def test_missing_commit_is_skipped(history):
    found = cogrepos.find_replacement(history.repo, "0" * 40, "cogA")
    assert found.commit is None


# ---------------------------------------------------------------- Red integration

RED_LAYOUT = None
try:  # Red 3.5.25.dev7+ keeps Downloader's state in redbot.core._downloader
    from redbot.core import _downloader as core_downloader
    from redbot.core._downloader import installable, repo_manager

    RED_LAYOUT = "core"
except ImportError:
    try:  # Red <= 3.5.24
        from redbot.cogs.downloader import (
            downloader as downloader_mod,
            installable,
            repo_manager,
        )

        RED_LAYOUT = "cog"
    except ImportError:
        pass

needs_red = pytest.mark.skipif(RED_LAYOUT is None, reason="needs Red-DiscordBot installed")


def make_installed(location, repo, commit, pinned=False):
    kwargs = {"install_location": location} if RED_LAYOUT == "core" else {}
    return installable.InstalledModule(
        location=location, repo=repo, commit=commit, pinned=pinned, json_repo_name=repo.name, **kwargs
    )


async def red_available_updates(fake, cogs, monkeypatch):
    """Run Red's real Downloader._available_updates against the fake store."""
    if RED_LAYOUT == "cog":
        fake_self = SimpleNamespace(
            installed_libraries=fake.installed_libraries, _save_to_installed=fake._save_to_installed
        )
        return await downloader_mod.Downloader._available_updates(fake_self, cogs)
    monkeypatch.setattr(core_downloader, "installed_libraries", fake.installed_libraries)
    monkeypatch.setattr(core_downloader, "_save_to_installed", fake._save_to_installed)
    return await core_downloader._available_updates(cogs)


class FakeDownloader:
    """Stands in for the Downloader cog: same method names, a dict instead of Config."""

    def __init__(self, modules):
        self.store = {(m.repo.name, m.name): m for m in modules}

    async def installed_cogs(self):
        return tuple(make_installed(m._location, m.repo, m.commit, m.pinned) for m in self.store.values())

    async def installed_libraries(self):
        return ()

    async def _save_to_installed(self, modules):
        for m in modules:
            self.store[(m.repo.name, m.name)] = make_installed(m._location, m.repo, m.commit, m.pinned)


def make_api(fake):
    return cogrepos.DownloaderAPI(fake.installed_cogs, fake.installed_libraries, fake._save_to_installed, "test")


@pytest.fixture
def red_setup(tmp_path):
    # Upstream with c1..c3, Red clones it at c3
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    run(upstream, "init", "-q", "-b", "main")
    write_module(upstream, "cogA", "v1")
    write_module(upstream, "cogB", "v1")
    write_module(upstream, "cogC", "v1")
    c1 = commit(upstream, "c1", 1_000)
    write_module(upstream, "cogB", "v2")
    c2 = commit(upstream, "c2", 2_000)
    write_module(upstream, "cogC", "v3-old")
    c3 = commit(upstream, "c3", 3_000)
    run(upstream, "config", "receive.denyCurrentBranch", "ignore")
    return SimpleNamespace(upstream=upstream, c=[c1, c2, c3], tmp=tmp_path)


async def clone_repo(setup):
    repo = repo_manager.Repo(
        name="vrt", url=str(setup.upstream), branch="main", commit="", folder_path=setup.tmp / "clone"
    )
    (setup.tmp / "clone").rmdir()
    await repo.clone()
    return repo


def installed(repo, name, commit, pinned=False):
    return make_installed(repo.folder_path / name, repo, commit, pinned)


@needs_red
@pytest.mark.asyncio
async def test_red_end_to_end(red_setup, monkeypatch):
    up = red_setup.upstream
    repo = await clone_repo(red_setup)
    c1, c2, c3 = red_setup.c
    assert repo.commit == c3

    # Force-push: same trees for c1, c2; c3 replaced by a commit that changes cogC differently
    n1, n2 = rewrite(up, [c1, c2], committer_date=9_000)
    run(up, "reset", "-q", "--hard", n2)
    write_module(up, "cogC", "v3-new")
    n3 = commit(up, "n3", 9_100)

    mods = [
        installed(repo, "cogA", c3),  # same tree as n3 (cogA never changed): identical
        installed(repo, "cogB", c2),  # v2 lives in n2 and n3: identical, newest n3
        installed(repo, "cogC", c3),  # v3-old exists nowhere new: code changed
        installed(repo, "cogP", c1, pinned=True),  # pinned: must be ignored
    ]
    # cogP needs a real folder for InstalledModule to read its info
    write_module(repo.folder_path, "cogP", "pinned")
    fake = FakeDownloader(mods)
    api = make_api(fake)

    # Red's own update path: first pull fails after a force-push, the retry succeeds
    with pytest.raises(repo_manager.errors.UpdateError):
        await repo.update()
    await repo.update()
    assert repo.commit == n3

    # Before the fix Red's _available_updates silently skips all three
    before_cogs, _ = await red_available_updates(fake, await fake.installed_cogs(), monkeypatch)
    assert before_cogs == ()
    assert fake.store[("vrt", "cogC")].commit == c3  # untouched

    result = await cogrepos.scan(api, update_repos=False)
    by_name = {fix.module.name: fix for fix in result.fixes}
    assert result.pinned == ["cogP"]
    assert "cogP" not in by_name
    assert by_name["cogA"].new_commit == n3 and by_name["cogA"].method == cogrepos.IDENTICAL
    assert by_name["cogB"].new_commit == n3 and by_name["cogB"].method == cogrepos.IDENTICAL
    # cogC: newest commit authored <= c3 (3000) with cogC != HEAD's is n2 (2000)
    assert by_name["cogC"].new_commit == n2 and by_name["cogC"].method == cogrepos.BY_DATE

    stored = await cogrepos.apply(api, result.fixes)
    assert stored == {"cogA": n3, "cogB": n3, "cogC": n2}
    assert fake.store[("vrt", "cogP")].commit == c1  # pinned record untouched

    # After the fix Red sees cogC as modified and offers the update
    after_cogs, _ = await red_available_updates(fake, await fake.installed_cogs(), monkeypatch)
    assert {m.name for m in after_cogs} == {"cogC"}

    # A second scan finds nothing stuck
    again = await cogrepos.scan(api, update_repos=False)
    assert again.fixes == []


@needs_red
@pytest.mark.asyncio
async def test_scan_updates_repo_with_retry(red_setup):
    up = red_setup.upstream
    repo = await clone_repo(red_setup)
    c1, c2, c3 = red_setup.c
    n1, n2, n3 = rewrite(up, [c1, c2, c3], committer_date=9_000)
    run(up, "reset", "-q", "--hard", n3)
    fake = FakeDownloader([installed(repo, "cogB", c3)])
    result = await cogrepos.scan(make_api(fake), update_repos=True)
    assert result.repos["vrt"].error == ""
    assert repo.commit == n3
    assert [(f.module.name, f.new_commit) for f in result.fixes] == [("cogB", n3)]


@needs_red
@pytest.mark.asyncio
async def test_unknown_revision_left_to_red(red_setup):
    repo = await clone_repo(red_setup)
    fake = FakeDownloader([installed(repo, "cogA", "1" * 40)])
    result = await cogrepos.scan(make_api(fake), update_repos=False)
    assert result.fixes == []
    assert result.red_handles == ["cogA"]


@needs_red
@pytest.mark.asyncio
async def test_missing_clone_reported(red_setup):
    repo = await clone_repo(red_setup)
    mod = installed(repo, "cogA", red_setup.c[0])
    import shutil

    shutil.rmtree(repo.folder_path / ".git")
    result = await cogrepos.scan(make_api(FakeDownloader([mod])), update_repos=False)
    assert result.fixes == []
    assert "no git clone" in result.repos["vrt"].error


def test_api_from_legacy_cog_and_missing_attrs():
    cog = SimpleNamespace(
        installed_cogs=lambda: None,
        installed_libraries=lambda: None,
        _save_to_installed=lambda m: None,
    )
    api = cogrepos.DownloaderAPI.from_cog(cog)
    if RED_LAYOUT == "core":
        # newer Red: the module-level functions win over the cog
        assert api.source == "redbot.core._downloader"
        assert api.save_to_installed is core_downloader._save_to_installed
        return
    assert api.source == "Downloader cog"
    assert api.save_to_installed is cog._save_to_installed
    with pytest.raises(RuntimeError, match="_save_to_installed"):
        cogrepos.DownloaderAPI.from_cog(SimpleNamespace(installed_cogs=1, installed_libraries=1))
