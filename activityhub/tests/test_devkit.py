"""
The devkit's files checked against the hub: the type hints, the test stand-ins, the template and the random number
generator
"""

import dataclasses
import inspect
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from activityhub.bundled.rng import Rng as BundledRng
from activityhub.common.sessions import ActivityContext
from activityhub.common.sockets import Connection, Room
from activityhub.devkit import fakes, hubtypes
from activityhub.devkit.rng import Rng

HUB = Path(__file__).resolve().parents[1]
DEVKIT = HUB / "devkit"
TEMPLATE = DEVKIT / "template" / "clickcounter"
GUIDE = (HUB / "DEVELOPERS.md").read_text(encoding="utf-8")
REFERENCE = (HUB / "REFERENCE.md").read_text(encoding="utf-8")
SDK = (HUB / "web" / "sdk.js").read_text(encoding="utf-8")
TYPES = (DEVKIT / "activityhub.d.ts").read_text(encoding="utf-8")
# Exports of sdk.js that the hub's own pages use. They aren't part of the API, so the type file leaves them out
INTERNAL_EXPORTS = {"request", "liveConnection", "liveOpener"}
# The hub's own working parts on a live connection. They aren't part of the API, so the type hints leave them out
INTERNAL_CONN_MEMBERS = {
    "close_after_sends",
    "closer",
    "closing",
    "drain",
    "end",
    "game",
    "inbox",
    "label",
    "let_go",
    "outbox",
    "outbox_size",
    "queue_text",
    "rooms",
    "send_text",
    "wake",
    "write",
    "writer",
    "ws",
}
# The hub's own working part on a room. It isn't part of the API, so the type hints leave it out
INTERNAL_ROOM_MEMBERS = {"members"}
# The quick start's code blocks, in order, and the template file each one is
QUICK_START_FILES = ["__init__.py", "info.json", "clickcounter.py", "web/index.html", "web/style.css", "web/game.js"]
FENCE = re.compile(r"^( *)```(\w*)\n(.*?)^\1```$", re.S | re.M)
SEEDS = [0, 1, 7, 123456789, 2**32 - 1, 3141592653]
COUNTS = [2, 7, 100, 1_000_000]
NODE_ROLLS = """
const { makeRng } = await import(process.argv[2]);
const seeds = JSON.parse(process.argv[3]);
const counts = JSON.parse(process.argv[4]);
console.log(JSON.stringify(seeds.map((seed) => {
  const rng = makeRng(seed);
  return { rolls: Array.from({ length: 50 }, () => rng.next()), picks: counts.map((count) => rng.pick(count)) };
})));
"""


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def protocol_members(protocol) -> set[str]:
    """The attributes, properties and methods a Protocol in hubtypes.py describes"""
    return {name for name in set(protocol.__annotations__) | set(vars(protocol)) if not name.startswith("_")}


def documented(text: str, prefix: str) -> set[str]:
    """The members a REFERENCE.md table lists as prefix.name, like `ctx.author` or **`await`** `conn.send(data)`"""
    return set(re.findall(rf"^\| (?:\*\*`await`\*\* )?`{prefix}\.(\w+)", text, re.M))


def awaited(owner, names: set[str]) -> dict[str, bool]:
    """For each method among names, whether it is an async def. Plain attributes and properties are left out"""
    # A Protocol's annotated attributes, like HubContext.author, have no value on the class at all
    values = {name: getattr(owner, name, None) for name in names}
    return {name: inspect.iscoroutinefunction(value) for name, value in values.items() if callable(value)}


def public_members(obj) -> set[str]:
    """The public attributes set on an object, plus the methods and properties its class defines"""
    methods = {
        name for name, value in vars(type(obj)).items() if inspect.isfunction(value) or isinstance(value, property)
    }
    return {name for name in set(vars(obj)) | methods if not name.startswith("_")}


def real_ctx_members() -> set[str]:
    methods = {
        name
        for name, value in vars(ActivityContext).items()
        if not name.startswith("_") and (inspect.isfunction(value) or isinstance(value, property))
    }
    # ctx.bot is for the hub itself: games use their own self.bot
    return ({field.name for field in dataclasses.fields(ActivityContext)} | methods) - {"bot"}


def test_the_ctx_type_hints_and_the_reference_match_the_real_ctx():
    members = real_ctx_members()
    assert protocol_members(hubtypes.HubContext) == members
    assert documented(section(REFERENCE, "## 2. `ctx`", "## 3. Handlers"), "ctx") == members
    assert awaited(hubtypes.HubContext, members) == awaited(ActivityContext, members)


def test_the_conn_and_room_type_hints_match_the_reference_and_the_hub():
    handlers = section(REFERENCE, "## 3. Handlers", "## 4. The page side")
    conn_members, room_members = protocol_members(hubtypes.HubConnection), protocol_members(hubtypes.HubRoom)
    assert documented(handlers, "conn") == conn_members
    assert documented(handlers, "room") == room_members
    conn, room = Connection(ws=None, ctx=None, game=None, rooms=None), Room("i-1", "i-1")
    assert {name for name in conn_members if not hasattr(conn, name)} == set()
    assert {name for name in room_members if not hasattr(room, name)} == set()
    # The other direction: a new public member of the real object fails here until it is documented or listed as internal
    assert public_members(conn) - INTERNAL_CONN_MEMBERS == conn_members
    assert public_members(room) - INTERNAL_ROOM_MEMBERS == room_members
    # And an internal name the hub no longer has fails too, so the lists can't hide a later member of the same name
    assert INTERNAL_CONN_MEMBERS - public_members(conn) == set()
    assert INTERNAL_ROOM_MEMBERS - public_members(room) == set()
    assert awaited(hubtypes.HubConnection, conn_members) == awaited(conn, conn_members)
    assert awaited(hubtypes.HubRoom, room_members) == awaited(room, room_members)


def test_the_test_stand_ins_have_everything_the_type_hints_list():
    ctx = fakes.player(1)
    room = fakes.FakeRoom()
    conn = fakes.FakeConn(ctx, room)
    for fake, protocol in ((ctx, hubtypes.HubContext), (conn, hubtypes.HubConnection), (room, hubtypes.HubRoom)):
        missing = {name for name in protocol_members(protocol) if not hasattr(fake, name)}
        assert missing == set(), f"{type(fake).__name__} has no {sorted(missing)}"


@pytest.mark.asyncio
async def test_the_fake_ctx_answers_what_the_test_set():
    assert await fakes.player(1).is_admin() is False
    assert await fakes.player(1).is_mod() is False
    assert await fakes.player(1, mod=True).is_mod() is True
    admin = fakes.player(1, admin=True)
    # Admins count as mods, like the real ctx
    assert await admin.is_admin() is True and await admin.is_mod() is True


@pytest.mark.asyncio
async def test_the_fake_conn_refuses_the_messages_the_hub_refuses():
    conn = fakes.FakeConn(fakes.player(1), fakes.FakeRoom())
    real = Connection(ws=None, ctx=None, game=None, rooms=None)
    for message in ({"activityhub": "ready"}, {"score": float("nan")}, {"score": float("inf")}):
        with pytest.raises(ValueError) as hub_error:
            await real.send(message)
        with pytest.raises(ValueError) as fake_error:
            await conn.send(message)
        if "activityhub" in message:
            assert str(fake_error.value) == str(hub_error.value)
    assert conn.sent == []
    # Only the top level is reserved, and an ordinary message is kept as the JSON the page would get
    await conn.send({"data": {"activityhub": 1}, "n": 1})
    assert conn.sent == [{"data": {"activityhub": 1}, "n": 1}]


def test_the_page_type_hints_list_every_hub_member_and_export():
    online = SDK[SDK.index("function onlineHub(") :]
    online = online[: online.index("\n}\n")]
    members = set(re.findall(r"^    (?:async |get )?(\w+)(?=[(:,])", online, re.M))
    hub_type = TYPES[TYPES.index("export interface Hub {") :]
    hub_type = hub_type[: hub_type.index("\n  }\n")]
    assert set(re.findall(r"^    (?:readonly )?(\w+)\??[(:]", hub_type, re.M)) == members
    assert documented(section(REFERENCE, "**The `hub` object**", "Catching an error"), "hub") == members
    exported = set(re.findall(r"^export (?:async )?(?:function\*?|class|const|let|var) (\w+)", SDK, re.M))
    # Exports in a list, or a default one, would slip past the line above
    assert re.search(r"^export (?:\{|\*|default)", SDK, re.M) is None, "export each name where it is defined"
    assert INTERNAL_EXPORTS <= exported
    assert set(re.findall(r"^  export (?:function|class) (\w+)", TYPES, re.M)) == exported - INTERNAL_EXPORTS


def test_the_template_is_the_quick_start():
    quick_start = section(GUIDE, "## 3. Quick start", "### Step 2")
    blocks = [match[3] for match in FENCE.finditer(quick_start) if match[2]]
    assert len(blocks) == len(QUICK_START_FILES)
    for name, block in zip(QUICK_START_FILES, blocks, strict=True):
        assert (TEMPLATE / name).read_text(encoding="utf-8") == block, f"{name} differs from the quick start"


def rolls(rng_class, seed: int) -> dict:
    rng = rng_class(seed)
    return {"rolls": [rng.next() for _ in range(50)], "picks": [rng.pick(count) for count in COUNTS]}


@pytest.fixture(scope="module")
def page_rolls(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so rng.js can't be run")
    script = tmp_path_factory.mktemp("node") / "rolls.mjs"
    script.write_text(NODE_ROLLS, encoding="utf-8")
    args = [node, str(script), (DEVKIT / "rng.js").as_uri(), json.dumps(SEEDS), json.dumps(COUNTS)]
    return json.loads(subprocess.run(args, capture_output=True, text=True, check=True, timeout=60).stdout)


def test_rng_py_and_rng_js_roll_the_same(page_rolls):
    assert page_rolls == [rolls(Rng, seed) for seed in SEEDS]


def test_the_devkit_rng_is_the_one_the_included_games_use():
    assert [rolls(Rng, seed) for seed in SEEDS] == [rolls(BundledRng, seed) for seed in SEEDS]
