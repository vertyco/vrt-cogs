import functools
import importlib.util
import inspect
import logging
import re
import sys
from pathlib import Path

import pytest

from activityhub.common import games
from activityhub.common.games import GameError, GameRegistry, validate_game

REMOVE = object()


class GameCog:
    """A stand-in game cog whose description can be bent per test"""

    def __init__(self, folder, cog_name="FakeGame", **changes):
        self.qualified_name = cog_name
        self.folder = folder
        self.changes = changes

    async def act(self, ctx, data):
        return {}

    async def join(self, ctx, conn):
        return None

    async def upload(self, request, ctx):
        return None

    async def activityhub_game(self):
        desc = {"key": "fake", "name": "Fake Game", "web_dir": self.folder, "actions": {"act": self.act}}
        desc.update(self.changes)
        return {k: v for k, v in desc.items() if v is not REMOVE}


class PlainCog:
    qualified_name = "Plain"


@pytest.fixture
def web_dir(tmp_path):
    (tmp_path / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
    (tmp_path / "icon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "wide.png").write_bytes(b"png")
    return tmp_path


@pytest.mark.asyncio
async def test_valid_description_becomes_a_game(web_dir):
    cog = GameCog(
        web_dir,
        icon="icon.svg",
        thumbnail="wide.png",
        socket={"join": None},
        routes={"POST /upload/": None},
        scopes=["guilds.members.read"],
    )
    cog.changes["socket"] = {"join": cog.join}
    cog.changes["routes"] = {"POST /upload/": cog.upload}
    game = await validate_game(cog)
    assert game.key == "fake" and game.name == "Fake Game" and game.cog is cog
    assert game.description == "" and game.icon == "icon.svg" and game.thumbnail == "wide.png"
    assert game.actions == {"act": cog.act}
    assert game.socket == {"join": cog.join}
    assert game.routes == {("POST", "upload"): cog.upload}
    assert game.scopes == ["guilds.members.read"]


@pytest.mark.asyncio
async def test_optional_fields_default(web_dir):
    game = await validate_game(GameCog(web_dir, actions=REMOVE))
    assert game.actions == {} and game.socket == {} and game.routes == {} and game.scopes == [] and game.icon is None
    assert game.thumbnail is None


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"action": {}}, r"Unknown field 'action' \(did you mean 'actions'\?\)"),
        ({"colour": 1, "zzz": 2}, r"Unknown fields: colour, zzz\. Check the spelling\. .* \(\[p\]cog update\)"),
        ({"web_dir": REMOVE}, "Missing fields: web_dir"),
        ({"key": "BB"}, "key"),
        ({"key": "a"}, "key"),
        ({"key": "x" * 33}, "key"),
        ({"key": "has space"}, "key"),
        ({"key": 5}, "key"),
        ({"name": "  "}, "name"),
        ({"description": 3}, "description"),
        ({"icon": "missing.png"}, "icon"),
        ({"icon": "../outside.svg"}, "icon"),
        ({"thumbnail": "missing.png"}, "thumbnail"),
        ({"thumbnail": "../outside.png"}, "thumbnail"),
        ({"thumbnail": 5}, "thumbnail"),
        ({"actions": []}, "actions must be a dict"),
        ({"socket": {"connect": None}}, "socket keys can only be 'join', 'message' and 'leave', got 'connect'"),
        ({"routes": {"FETCH data": None}}, "routes"),
        ({"routes": {"GET /": None}}, "routes"),
        ({"scopes": "identify"}, "scopes"),
        ({"scopes": [""]}, "scopes must be a list of strings"),
    ],
)
@pytest.mark.asyncio
async def test_bad_descriptions_are_refused(web_dir, changes, reason):
    with pytest.raises(GameError, match=reason):
        await validate_game(GameCog(web_dir, **changes))


@pytest.mark.asyncio
async def test_web_dir_needs_an_index(tmp_path):
    with pytest.raises(GameError, match="index.html"):
        await validate_game(GameCog(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["has space", "a/b", "x" * 65, "", ".", "..", 5])
async def test_action_names_are_checked(web_dir, name):
    cog = GameCog(web_dir)
    cog.changes["actions"] = {name: cog.act}
    with pytest.raises(GameError, match=f"actions key {re.escape(repr(name))} must be 1-64 letters, digits"):
        await validate_game(cog)


@pytest.mark.asyncio
async def test_action_names_with_dots_are_fine_when_not_only_dots(web_dir):
    cog = GameCog(web_dir)
    cog.changes["actions"] = {"save.v2": cog.act, "a..b": cog.act}
    assert set((await validate_game(cog)).actions) == {"save.v2", "a..b"}


@pytest.mark.asyncio
async def test_handlers_must_be_async(web_dir):
    def sync_handler(ctx, data):
        return {}

    with pytest.raises(GameError, match="async def"):
        await validate_game(GameCog(web_dir, actions={"act": sync_handler}))


@pytest.mark.asyncio
async def test_plain_def_hook_is_refused(web_dir):
    class PlainHookCog(GameCog):
        def activityhub_game(self):
            return {}

    with pytest.raises(GameError, match="must be an async def"):
        await validate_game(PlainHookCog(web_dir))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "returned, reason",
    [
        ([], r"must return one dict \(one game per cog\), got list"),
        (None, "must return a dict, got NoneType"),
        ("snake", "must return a dict, got str"),
    ],
)
async def test_hook_must_return_a_dict(web_dir, returned, reason):
    class OddHookCog(GameCog):
        async def activityhub_game(self):
            return returned

    with pytest.raises(GameError, match=reason):
        await validate_game(OddHookCog(web_dir))


@pytest.mark.asyncio
async def test_registry_adds_games_and_ignores_plain_cogs(web_dir):
    registry = GameRegistry()
    assert await registry.add(PlainCog()) is None
    assert registry.failed == {}
    game = await registry.add(GameCog(web_dir, scopes=["b.scope", "a.scope"]))
    assert registry.games == {"fake": game}
    assert registry.scopes() == ["a.scope", "b.scope"]


@pytest.mark.asyncio
async def test_registry_records_refusals(web_dir):
    registry = GameRegistry()
    cog = GameCog(web_dir, key="NOPE")
    assert await registry.add(cog) is None
    assert registry.failed["FakeGame"][0] is cog
    assert "key" in registry.failed["FakeGame"][1]


@pytest.mark.asyncio
async def test_registry_records_a_raising_hook(web_dir, caplog):
    class BrokenCog(GameCog):
        async def activityhub_game(self):
            raise RuntimeError("boom")

    registry = GameRegistry()
    assert await registry.add(BrokenCog(web_dir)) is None
    assert registry.failed["FakeGame"][1] == "activityhub_game() raised RuntimeError: boom"
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_first_cog_keeps_a_duplicate_key(web_dir):
    registry = GameRegistry()
    first = await registry.add(GameCog(web_dir, cog_name="First"))
    assert await registry.add(GameCog(web_dir, cog_name="Second")) is None
    assert registry.games["fake"] is first
    assert "already used by First" in registry.failed["Second"][1]


@pytest.mark.asyncio
async def test_reload_remove_then_add(web_dir):
    registry = GameRegistry()
    old, new = GameCog(web_dir), GameCog(web_dir)
    await registry.add(old)
    registry.remove(old)
    await registry.add(new)
    assert registry.games["fake"].cog is new


@pytest.mark.asyncio
async def test_reload_add_before_remove_keeps_new_copy(web_dir):
    registry = GameRegistry()
    old, new = GameCog(web_dir), GameCog(web_dir)
    await registry.add(old)
    await registry.add(new)
    registry.remove(old)
    assert registry.games["fake"].cog is new


@pytest.mark.asyncio
async def test_reload_with_a_new_key_drops_the_old_key(web_dir):
    registry = GameRegistry()
    await registry.add(GameCog(web_dir))
    await registry.add(GameCog(web_dir, key="renamed"))
    assert list(registry.games) == ["renamed"]


@pytest.mark.asyncio
async def test_failed_new_copy_survives_old_copy_removal(web_dir):
    registry = GameRegistry()
    old, broken = GameCog(web_dir), GameCog(web_dir, key="BAD")
    await registry.add(old)
    await registry.add(broken)
    registry.remove(old)
    assert registry.games == {}
    assert registry.failed["FakeGame"][0] is broken


@pytest.mark.asyncio
async def test_removing_a_cog_clears_its_failure(web_dir):
    registry = GameRegistry()
    broken = GameCog(web_dir, key="BAD")
    await registry.add(broken)
    registry.remove(broken)
    assert registry.failed == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key, message",
    [
        (
            "Click_Counter",
            "key must be 2-32 characters of a-z, 0-9 and hyphens, got 'Click_Counter' (try 'click-counter')",
        ),
        ("x" * 33, f"key must be 2-32 characters of a-z, 0-9 and hyphens, got '{'x' * 33}' (try '{'x' * 32}')"),
        ("a", "key must be 2-32 characters of a-z, 0-9 and hyphens, got 'a'"),
        (5, "key must be 2-32 characters of a-z, 0-9 and hyphens, got 5"),
    ],
)
async def test_a_refused_key_is_shown_with_a_fix(web_dir, key, message):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, key=key))
    assert str(refused.value) == message


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["GET score/{id}", "post x", "x", "GET a/../b", "GET ./a", "GET a/.", 5])
async def test_route_names_are_refused_with_the_rule(web_dir, name):
    cog = GameCog(web_dir)
    cog.changes["routes"] = {name: cog.upload}
    with pytest.raises(GameError) as refused:
        await validate_game(cog)
    assert str(refused.value).startswith(f'routes key {name!r} must be "METHOD path": GET, POST, PUT, PATCH or DELETE')
    assert str(refused.value).endswith("there are no {parameters}: read values from request.query instead.")


@pytest.mark.asyncio
async def test_a_route_listed_twice_is_refused(web_dir):
    cog = GameCog(web_dir)
    cog.changes["routes"] = {"GET a": cog.upload, "GET /a/": cog.upload}
    with pytest.raises(GameError, match=re.escape("routes has 'GET /a/' twice (paths ignore leading and trailing /)")):
        await validate_game(cog)
    cog.changes["routes"] = {"GET a": cog.upload, "POST a": cog.upload}
    assert set((await validate_game(cog)).routes) == {("GET", "a"), ("POST", "a")}


@pytest.mark.asyncio
async def test_a_called_handler_is_refused_and_closed(web_dir):
    cog = GameCog(web_dir)
    called = cog.act(None, {})
    cog.changes["actions"] = {"act": called}
    with pytest.raises(GameError) as refused:
        await validate_game(cog)
    assert str(refused.value) == "actions 'act' is a coroutine, not a method: write self.act without ()"
    # Python only warns "never awaited" about a coroutine that wasn't closed
    assert inspect.getcoroutinestate(called) == inspect.CORO_CLOSED


def passes_through(func):
    """A decorator that isn't async itself, like many logging or timing decorators"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


class AsyncCallable:
    async def __call__(self, ctx, data):
        return {}


class HandlerCog(GameCog):
    """Handlers written in every way the hub can and can't call"""

    @passes_through
    async def wrapped(self, ctx, data):
        return {}

    async def optional_data(self, ctx, data=None):
        return {}

    async def star_args(self, ctx, *args):
        return {}

    async def no_data(self, ctx):
        return {}

    async def keyword_only(self, ctx, data, *, extra):
        return {}

    async def join_without_conn(self, ctx):
        return None

    async def message_without_data(self, ctx, conn):
        return None

    async def swapped_route(self, ctx, request):
        return None


@pytest.mark.asyncio
async def test_handlers_the_hub_can_call_are_accepted(web_dir):
    cog = HandlerCog(web_dir)
    actions = {
        "wrapped": cog.wrapped,
        "callable": AsyncCallable(),
        "optional": cog.optional_data,
        "star": cog.star_args,
        "partial": functools.partial(cog.act),
    }
    cog.changes["actions"] = actions
    assert (await validate_game(cog)).actions == actions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field, name, method, message",
    [
        ("actions", "act", "no_data", "actions handler 'act' takes (ctx), but the hub calls it with (ctx, data)."),
        (
            "actions",
            "act",
            "keyword_only",
            "actions handler 'act' takes (ctx, data, *, extra), but the hub calls it with (ctx, data).",
        ),
        (
            "socket",
            "join",
            "join_without_conn",
            "socket handler 'join' takes (ctx), but the hub calls it with (ctx, conn).",
        ),
        (
            "socket",
            "message",
            "message_without_data",
            "socket handler 'message' takes (ctx, conn), but the hub calls it with (ctx, conn, data).",
        ),
        (
            "routes",
            "GET a",
            "swapped_route",
            "routes handler 'GET a' takes (ctx, request), but raw routes get (request, ctx): request first",
        ),
    ],
)
async def test_handlers_with_the_wrong_arguments_are_refused(web_dir, field, name, method, message):
    cog = HandlerCog(web_dir)
    cog.changes[field] = {name: getattr(cog, method)}
    with pytest.raises(GameError) as refused:
        await validate_game(cog)
    assert str(refused.value) == message


@pytest.mark.asyncio
async def test_a_method_taken_from_the_class_gets_a_hint(web_dir):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, actions={"act": GameCog.act}))
    assert str(refused.value) == (
        "actions handler 'act' takes (self, ctx, data), but the hub calls it with (ctx, data). "
        "Use self.act, not GameCog.act."
    )


@pytest.mark.asyncio
async def test_picture_paths_are_kept_relative_to_web_dir(web_dir):
    for icon in (web_dir / "icon.svg", str(web_dir / "icon.svg"), Path("icon.svg"), "icon.svg"):
        assert (await validate_game(GameCog(web_dir, icon=icon))).icon == "icon.svg"


@pytest.mark.asyncio
async def test_a_picture_outside_web_dir_is_refused(web_dir, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "icon.svg"
    outside.write_text("<svg/>", encoding="utf-8")
    for icon in (outside, str(outside), web_dir / "missing.png"):
        with pytest.raises(GameError) as refused:
            await validate_game(GameCog(web_dir, icon=icon))
        assert str(refused.value) == (
            f"icon must be a file inside web_dir, written relative to it (like 'icon.png'): {icon}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["identify guilds", "rpc.activities.write,identify", " x", "Identify"])
async def test_scope_names_are_checked(web_dir, scope):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, scopes=["identify", scope]))
    assert str(refused.value) == (
        f"scopes has {scope!r}, which isn't a Discord scope name. "
        'Write one scope per string, like ["identify", "guilds"].'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["bot", "webhook.incoming"])
async def test_scopes_a_login_cannot_ask_for_are_refused(web_dir, scope):
    reason = f"scopes can't include '{scope}': it isn't a permission an Activity login can ask for"
    with pytest.raises(GameError, match=re.escape(reason)):
        await validate_game(GameCog(web_dir, scopes=[scope]))


@pytest.mark.asyncio
async def test_an_unknown_scope_registers_with_a_warning(web_dir, caplog):
    game = await validate_game(GameCog(web_dir, scopes=["rpc.activity.write"]))
    assert game.scopes == ["rpc.activity.write"]
    assert "FakeGame asks for the scope 'rpc.activity.write', which ActivityHub doesn't know" in caplog.text


@pytest.mark.asyncio
async def test_a_known_scope_registers_quietly(web_dir, caplog):
    game = await validate_game(GameCog(web_dir, scopes=["rpc.activities.write"]))
    assert game.scopes == ["rpc.activities.write"]
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_known_scopes_match_the_vendored_discord_sdk():
    sdk = Path(games.__file__).parent.parent / "web" / "vendor" / "discord-sdk.js"
    listed = re.search(r'\[("identify",[^\]]*)\]', sdk.read_text(encoding="utf-8"))
    assert set(re.findall(r'"([^"]+)"', listed[1])) == games.KNOWN_SCOPES


COG_SOURCE = """class FolderCog:
    qualified_name = "FolderCog"

    def __init__(self, web_dir):
        self.web_dir = web_dir

    async def activityhub_game(self):
        return {"key": "folder", "name": "Folder", "web_dir": self.web_dir}
"""


@pytest.fixture
def cog_folder(tmp_path, monkeypatch):
    """A cog's own folder holding its cog.py, loaded the way Red loads one. Gives the folder and the cog class"""
    folder = tmp_path / "foldercog"
    folder.mkdir()
    (folder / "cog.py").write_text(COG_SOURCE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("foldercog_for_tests", folder / "cog.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return folder.resolve(), module.FolderCog


def write_index(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
    return folder


@pytest.mark.asyncio
async def test_a_relative_web_dir_starts_at_the_cogs_folder(cog_folder, tmp_path, monkeypatch):
    folder, FolderCog = cog_folder
    write_index(folder / "web")
    # Pyodide games ship .py files of their own, so those are fine
    (folder / "web" / "engine.py").write_text("print('hi')\n", encoding="utf-8")
    monkeypatch.chdir(write_index(tmp_path / "elsewhere"))
    for web_dir in ("web", Path("web"), "./web"):
        assert (await validate_game(FolderCog(web_dir))).web_dir.resolve() == folder / "web"


@pytest.mark.asyncio
async def test_a_missing_index_shows_the_full_path_tried(cog_folder):
    folder, FolderCog = cog_folder
    with pytest.raises(GameError) as refused:
        await validate_game(FolderCog("web"))
    assert str(refused.value) == f"web_dir has no index.html: looked for {folder / 'web' / 'index.html'}"


@pytest.mark.asyncio
async def test_web_dir_cannot_hold_the_cogs_code(cog_folder):
    folder, FolderCog = cog_folder
    write_index(folder)
    write_index(folder.parent)
    for web_dir in (".", "..", folder):
        with pytest.raises(GameError) as refused:
            await validate_game(FolderCog(web_dir))
        assert str(refused.value) == (
            "web_dir holds your cog's Python code, and everything in web_dir is public. "
            'Keep the page in its own folder, like Path(__file__).parent / "web".'
        )


@pytest.mark.asyncio
async def test_web_dir_expands_the_home_folder(web_dir, monkeypatch):
    # Windows reads the home folder from USERPROFILE, everything else from HOME
    monkeypatch.setenv("HOME", str(web_dir.parent))
    monkeypatch.setenv("USERPROFILE", str(web_dir.parent))
    assert (await validate_game(GameCog(f"~/{web_dir.name}"))).web_dir == web_dir


@pytest.mark.asyncio
async def test_a_cog_class_with_no_file_keeps_web_dir_as_written(web_dir, monkeypatch):
    NoFileCog = type("NoFileCog", (GameCog,), {"__module__": "typed_into_a_repl"})
    monkeypatch.chdir(web_dir.parent)
    assert (await validate_game(NoFileCog(web_dir.name))).web_dir == Path(web_dir.name)


@pytest.mark.asyncio
async def test_index_must_be_utf8(web_dir):
    (web_dir / "index.html").write_text("<html><head><title>Café</title></head></html>", encoding="cp1252")
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir))
    assert str(refused.value) == "index.html isn't UTF-8 text (invalid continuation byte at byte 22). Save it as UTF-8."


@pytest.mark.asyncio
async def test_absolute_paths_in_the_page_are_warned_about(web_dir, caplog):
    page = '<html><head><script type="module" src="/assets/x.js"></script></head></html>'
    (web_dir / "index.html").write_text(page, encoding="utf-8")
    assert await validate_game(GameCog(web_dir)) is not None
    assert "fake: index.html refers to /assets/x.js with an absolute path, which the hub can't serve" in caplog.text


@pytest.mark.asyncio
async def test_relative_paths_and_other_websites_are_not_warned_about(web_dir, caplog):
    page = (
        '<html><head><script src="game.js"></script><link href="//cdn.example.com/x.css" />'
        "<a href='https://example.com/'>site</a></head></html>"
    )
    (web_dir / "index.html").write_text(page, encoding="utf-8")
    await validate_game(GameCog(web_dir))
    assert "absolute path" not in caplog.text


@pytest.mark.asyncio
async def test_node_modules_in_web_dir_is_warned_about(web_dir, caplog):
    (web_dir / "node_modules" / "left-pad").mkdir(parents=True)
    await validate_game(GameCog(web_dir))
    assert "fake: web_dir has a node_modules folder. Every file in it is public" in caplog.text


@pytest.mark.asyncio
async def test_a_huge_web_dir_is_warned_about(web_dir, caplog, monkeypatch):
    monkeypatch.setattr(games, "MANY_FILES", 3)
    # index.html, icon.svg and wide.png
    await validate_game(GameCog(web_dir))
    assert "web_dir has" not in caplog.text
    (web_dir / "extra.js").write_text("", encoding="utf-8")
    await validate_game(GameCog(web_dir))
    assert "fake: web_dir has more than 3 files. Every file in it is public" in caplog.text


@pytest.mark.asyncio
async def test_hidden_files_dont_make_web_dir_huge(web_dir, caplog, monkeypatch):
    # A web_dir that is a git checkout: .git is never served or fingerprinted, so it isn't counted
    monkeypatch.setattr(games, "MANY_FILES", 3)
    (web_dir / ".git" / "objects").mkdir(parents=True)
    for name in ("a", "b", "c"):
        (web_dir / ".git" / "objects" / name).write_text("", encoding="utf-8")
    await validate_game(GameCog(web_dir))
    assert "web_dir has" not in caplog.text


@pytest.mark.asyncio
async def test_a_hidden_picture_is_refused(web_dir):
    # Hidden files are never served, so the menu couldn't show it
    (web_dir / ".icons").mkdir()
    (web_dir / ".icons" / "icon.svg").write_text("<svg/>", encoding="utf-8")
    for icon in (".icons/icon.svg", web_dir / ".icons" / "icon.svg"):
        with pytest.raises(GameError) as refused:
            await validate_game(GameCog(web_dir, icon=icon))
        assert str(refused.value) == (
            f"icon has a name starting with a dot in its path, and the hub never serves those: {icon}"
        )


@pytest.mark.asyncio
async def test_registry_remembers_which_key_a_refused_cog_wanted(web_dir):
    registry = GameRegistry()
    await registry.add(GameCog(web_dir, cog_name="First"))
    second = GameCog(web_dir, cog_name="Second")
    await registry.add(second)
    # Refused for another reason, so not waiting for a key
    await registry.add(GameCog(web_dir, cog_name="Broken", key="BAD"))
    assert registry.clashes == {"Second": "fake"}
    registry.remove(second)
    assert registry.clashes == {}
    await registry.add(second)
    second.changes["key"] = "other"
    await registry.add(second)
    assert registry.games["other"].cog is second and registry.clashes == {}
