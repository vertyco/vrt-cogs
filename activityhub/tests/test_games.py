import asyncio
import functools
import importlib.util
import inspect
import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from activityhub.bundled.games import Snake
from activityhub.common import games
from activityhub.common.games import VERSION_PATTERN, GameError, GameRegistry, validate_game
from activityhub.main import ActivityHub
from activityhub.tests.fakes import make_hub

REMOVE = object()
HUB_VERSION = "0.8.0"


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

    async def upload(self, ctx, request):
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
    registry = GameRegistry(HUB_VERSION)
    assert await registry.add(PlainCog()) is None
    assert registry.failed == {}
    game = await registry.add(GameCog(web_dir, scopes=["b.scope", "a.scope"]))
    assert registry.games == {"fake": game}
    assert registry.scopes() == ["a.scope", "b.scope"]


@pytest.mark.asyncio
async def test_registry_records_refusals(web_dir):
    registry = GameRegistry(HUB_VERSION)
    cog = GameCog(web_dir, key="NOPE")
    assert await registry.add(cog) is None
    assert registry.failed["FakeGame"][0] is cog
    assert "key" in registry.failed["FakeGame"][1]


@pytest.mark.asyncio
async def test_registry_records_a_raising_hook(web_dir, caplog):
    class BrokenCog(GameCog):
        async def activityhub_game(self):
            raise RuntimeError("boom")

    registry = GameRegistry(HUB_VERSION)
    assert await registry.add(BrokenCog(web_dir)) is None
    assert registry.failed["FakeGame"][1] == "activityhub_game() raised RuntimeError: boom"
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_first_cog_keeps_a_duplicate_key(web_dir):
    registry = GameRegistry(HUB_VERSION)
    first = await registry.add(GameCog(web_dir, cog_name="First"))
    assert await registry.add(GameCog(web_dir, cog_name="Second")) is None
    assert registry.games["fake"] is first
    assert "already used by First" in registry.failed["Second"][1]


@pytest.mark.asyncio
async def test_reload_remove_then_add(web_dir):
    registry = GameRegistry(HUB_VERSION)
    old, new = GameCog(web_dir), GameCog(web_dir)
    await registry.add(old)
    registry.remove(old)
    await registry.add(new)
    assert registry.games["fake"].cog is new


@pytest.mark.asyncio
async def test_reload_add_before_remove_keeps_new_copy(web_dir):
    registry = GameRegistry(HUB_VERSION)
    old, new = GameCog(web_dir), GameCog(web_dir)
    await registry.add(old)
    await registry.add(new)
    registry.remove(old)
    assert registry.games["fake"].cog is new


@pytest.mark.asyncio
async def test_reload_with_a_new_key_drops_the_old_key(web_dir):
    registry = GameRegistry(HUB_VERSION)
    await registry.add(GameCog(web_dir))
    await registry.add(GameCog(web_dir, key="renamed"))
    assert list(registry.games) == ["renamed"]


@pytest.mark.asyncio
async def test_failed_new_copy_survives_old_copy_removal(web_dir):
    registry = GameRegistry(HUB_VERSION)
    old, broken = GameCog(web_dir), GameCog(web_dir, key="BAD")
    await registry.add(old)
    await registry.add(broken)
    registry.remove(old)
    assert registry.games == {}
    assert registry.failed["FakeGame"][0] is broken


@pytest.mark.asyncio
async def test_removing_a_cog_clears_its_failure(web_dir):
    registry = GameRegistry(HUB_VERSION)
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

    async def swapped_route(self, request, ctx):
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
            "routes handler 'GET a' takes (request, ctx), but raw routes get (ctx, request): ctx first",
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
    registry = GameRegistry(HUB_VERSION)
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


class EconomyCog(GameCog):
    async def line(self, ctx):
        return "Earn credits"

    async def no_args(self):
        return None

    def sync_line(self, ctx):
        return "Earn credits"


@pytest.mark.asyncio
async def test_economy_defaults_to_none(web_dir):
    assert (await validate_game(GameCog(web_dir))).economy is None


@pytest.mark.asyncio
@pytest.mark.parametrize("value, kept", [(None, None), ("  Earn credits  ", "Earn credits"), ("   ", None)])
async def test_economy_fixed_lines(web_dir, value, kept):
    assert (await validate_game(GameCog(web_dir, economy=value))).economy == kept


@pytest.mark.asyncio
async def test_economy_function_is_kept(web_dir):
    cog = EconomyCog(web_dir)
    cog.changes["economy"] = cog.line
    assert (await validate_game(cog)).economy == cog.line


@pytest.mark.asyncio
async def test_economy_line_over_the_limit_is_refused(web_dir):
    with pytest.raises(GameError, match="economy is 41 characters long, but the menu's badge fits 40"):
        await validate_game(GameCog(web_dir, economy="x" * 41))


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, 5, ["Earn"], {"text": "Earn"}])
async def test_economy_of_the_wrong_type_is_refused(web_dir, value):
    with pytest.raises(GameError, match="economy must be None, a string, or an async def that takes ctx"):
        await validate_game(GameCog(web_dir, economy=value))


@pytest.mark.asyncio
async def test_economy_function_must_be_async(web_dir):
    cog = EconomyCog(web_dir)
    cog.changes["economy"] = cog.sync_line
    with pytest.raises(GameError, match="economy must be None, a string, or an async def"):
        await validate_game(cog)


@pytest.mark.asyncio
async def test_economy_function_must_take_ctx(web_dir):
    cog = EconomyCog(web_dir)
    cog.changes["economy"] = cog.no_args
    with pytest.raises(GameError, match=r"economy takes \(\), but the hub calls it with \(ctx\)"):
        await validate_game(cog)


@pytest.mark.asyncio
async def test_economy_called_by_mistake_is_refused(web_dir):
    cog = EconomyCog(web_dir)
    cog.changes["economy"] = cog.line(None)
    with pytest.raises(GameError, match=r"economy is a coroutine, not a method: write self.line without \(\)"):
        await validate_game(cog)


@pytest.mark.asyncio
@pytest.mark.parametrize("requires", ["0.8", "0.8.0", "0.7.9", "0.0.1"])
async def test_a_game_for_this_hub_or_an_older_one_registers(web_dir, requires):
    registry = GameRegistry("0.8.0")
    assert await registry.add(GameCog(web_dir, requires=requires)) is not None


@pytest.mark.asyncio
async def test_the_registry_refuses_a_game_for_a_newer_hub(web_dir):
    registry = GameRegistry("0.8.0")
    assert await registry.add(GameCog(web_dir, requires="0.9.0")) is None
    assert registry.games == {}
    assert registry.failed["FakeGame"][1].startswith("This game needs ActivityHub 0.9.0 or newer")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requires, hub_version", [("0.9.0", "0.8.0"), ("0.8.1", "0.8.0"), ("0.10", "0.9.5"), ("1.0", "0.8.0")]
)
async def test_a_game_for_a_newer_hub_says_to_update(web_dir, requires, hub_version):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, requires=requires), hub_version)
    assert str(refused.value) == (
        f"This game needs ActivityHub {requires} or newer, and this bot has {hub_version}. "
        "Update it: [p]cog update activityhub"
    )


@pytest.mark.asyncio
async def test_the_version_is_checked_before_unknown_fields(web_dir):
    # A game made for a newer hub may use fields this hub doesn't know yet
    cog = GameCog(web_dir, requires="9.0.0", leaderboard=True)
    with pytest.raises(GameError, match="This game needs ActivityHub 9.0.0 or newer"):
        await validate_game(cog, "0.8.0")


@pytest.mark.asyncio
@pytest.mark.parametrize("requires", ["latest", "0.8.", "v0.8", "0.8.0.1", "8", "", "０.８", 0.8, None, ["0", "8"]])
async def test_a_requires_that_isnt_a_version_is_refused(web_dir, requires):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, requires=requires), "0.8.0")
    assert str(refused.value) == f'requires must be a version like "0.8.0", got {requires!r}'


@pytest.mark.asyncio
@pytest.mark.parametrize("requires", ["1234567890.0", "0." + "9" * 5000])
async def test_a_requires_with_a_huge_number_gets_the_version_message(web_dir, requires):
    # Past Python's limit on turning text into an int, the refusal would otherwise be a bare ValueError
    with pytest.raises(GameError, match='requires must be a version like "0.8.0"'):
        await validate_game(GameCog(web_dir, requires=requires), "0.8.0")


def test_the_hubs_own_version_is_one_requires_can_be_compared_with():
    # Only plain numbers compare. A version like 0.9.0b1 would make every game with requires fail to load
    assert VERSION_PATTERN.fullmatch(ActivityHub.__version__) is not None


@pytest.mark.asyncio
async def test_without_a_hub_version_only_the_shape_is_checked(web_dir):
    # Game cogs' own tests call validate_game like this, to check their description
    assert await validate_game(GameCog(web_dir, requires="99.0")) is not None


@pytest.mark.asyncio
async def test_a_misspelt_requires_gets_a_suggestion(web_dir):
    with pytest.raises(GameError, match=re.escape("Unknown field 'require' (did you mean 'requires'?)")):
        await validate_game(GameCog(web_dir, require="0.8.0"), "0.8.0")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["hub-", "hub-snake"])
async def test_hub_keys_are_kept_for_the_included_games(web_dir, key):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, key=key))
    assert str(refused.value) == "keys starting with 'hub-' are kept for ActivityHub's own games"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["hub", "hubble", "my-hub-game"])
async def test_keys_that_only_look_like_hub_keys_are_fine(web_dir, key):
    assert (await validate_game(GameCog(web_dir, key=key))).key == key


class HubSnake(Snake):
    """An included game on a hub- key, like the ones ActivityHub will add"""

    async def activityhub_game(self) -> dict:
        return {**await super().activityhub_game(), "key": "hub-snake"}


@pytest.mark.asyncio
async def test_an_included_game_can_use_a_hub_key():
    hub = make_hub()
    assert (await validate_game(HubSnake(hub.scores, hub.payouts), included=True)).key == "hub-snake"
    # Only the hub registering it as included counts, not which class the game comes from
    with pytest.raises(GameError):
        await validate_game(HubSnake(hub.scores, hub.payouts))


@pytest.mark.asyncio
async def test_platforms_default_to_both(web_dir):
    assert (await validate_game(GameCog(web_dir))).platforms == ["desktop", "mobile"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value, kept",
    [(["desktop"], ["desktop"]), (["mobile", "mobile"], ["mobile"]), (["mobile", "desktop"], ["mobile", "desktop"])],
)
async def test_platforms_are_kept_once_each(web_dir, value, kept):
    assert (await validate_game(GameCog(web_dir, platforms=value))).platforms == kept


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [["ios"], ["Desktop"], ["web"], "desktop", None, [1], ("desktop",)])
async def test_platforms_only_know_desktop_and_mobile(web_dir, value):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, platforms=value))
    assert str(refused.value) == (
        f'platforms can only hold "desktop" and "mobile" (all Discord tells the hub), got {value!r}'
    )


@pytest.mark.asyncio
async def test_platforms_cant_be_empty(web_dir):
    with pytest.raises(GameError, match="platforms can't be empty: leave it out to run everywhere"):
        await validate_game(GameCog(web_dir, platforms=[]))


@pytest.mark.asyncio
async def test_room_defaults_to_one_window(web_dir):
    assert (await validate_game(GameCog(web_dir))).room == "window"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["window", "server", "everywhere"])
async def test_room_takes_window_server_or_everywhere(web_dir, value):
    assert (await validate_game(GameCog(web_dir, room=value))).room == value


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["guild", "Server", "", None, ["server"]])
async def test_room_refuses_anything_else(web_dir, value):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, room=value))
    assert str(refused.value) == (
        f'room must be "window", "server", "everywhere", or an async def that takes ctx, got {value!r}'
    )


@pytest.mark.asyncio
async def test_room_can_be_a_function_of_the_player(web_dir):
    async def pick(ctx):
        return "server"

    assert (await validate_game(GameCog(web_dir, room=pick))).room is pick


@pytest.mark.asyncio
async def test_a_room_function_must_be_an_async_def_taking_ctx(web_dir):
    def plain(ctx):
        return "server"

    async def two(ctx, extra):
        return "server"

    async def pick(ctx):
        return "server"

    with pytest.raises(GameError, match="or an async def that takes ctx, got <function"):
        await validate_game(GameCog(web_dir, room=plain))
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, room=two))
    assert str(refused.value) == "room takes (ctx, extra), but the hub calls it with (ctx)."
    called = pick(None)
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, room=called))
    assert str(refused.value) == "room is a coroutine, not a method: write self.pick without ()"


def room_game(room):
    return games.Game(key="picky", name="Picky", web_dir=Path("."), cog=None, room=room)


@pytest.mark.asyncio
async def test_a_room_function_picks_each_players_room():
    async def pick(ctx):
        return "everywhere" if ctx.author == 1 else "window"

    game = room_game(pick)
    assert await game.room_kind(SimpleNamespace(author=1)) == "everywhere"
    assert await game.room_kind(SimpleNamespace(author=2)) == "window"


@pytest.mark.asyncio
async def test_a_broken_room_function_keeps_the_player_in_their_window(caplog, monkeypatch):
    async def broken(ctx):
        raise RuntimeError("no settings")

    async def wrong(ctx):
        return "guild"

    async def slow(ctx):
        await asyncio.sleep(1)
        return "server"

    monkeypatch.setattr(games, "ROOM_WAIT", 0.05)
    with caplog.at_level(logging.WARNING, logger="red.vrt.activityhub.games"):
        assert await room_game(broken).room_kind(None) == "window"
        assert await room_game(wrong).room_kind(None) == "window"
        assert await room_game(slow).room_kind(None) == "window"
    assert "picky: room failed, so the player plays in their own window" in caplog.text
    assert "picky: room returned 'guild'" in caplog.text
    assert "picky: room took longer than 0.05 seconds, so the player plays in their own window" in caplog.text


@pytest.mark.asyncio
async def test_opens_in_defaults_to_everywhere(web_dir):
    assert (await validate_game(GameCog(web_dir))).opens_in == "everywhere"


@pytest.mark.asyncio
async def test_opens_in_can_be_servers_only(web_dir):
    assert (await validate_game(GameCog(web_dir, opens_in="server"))).opens_in == "server"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["servers", "Server", "window", ["server"], None, 1])
async def test_opens_in_only_knows_server_and_everywhere(web_dir, value):
    with pytest.raises(GameError) as refused:
        await validate_game(GameCog(web_dir, opens_in=value))
    assert str(refused.value) == f'opens_in must be "server" or "everywhere", got {value!r}'
