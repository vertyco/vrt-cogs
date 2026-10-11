import pytest

from botarena3.common import battle as engine
from botarena3.common.lobby import STEPS, Window
from botarena3.tests.fakes import FakeConn, FakeRoom
from botarena3.tests.helpers import robot


def window(room=None):
    results = []
    return Window(room or FakeRoom(), results.append, lambda w: None), results


async def solo(win, conn, kind="arena"):
    return await win.add_run(
        kind,
        0,
        "ROXTAN PARK ARENA",
        1,
        ([robot()], [robot(weapon=None)]),
        (1, 9),
        {conn.ctx.author.id: 1},
        [conn.ctx.author.display_name, None],
        {conn.ctx.author.id: "Global"},
        owned=(True, False),
        draws=False,
    )


def sent(conn, key):
    return [m[key] for m in conn.sent if key in m]


@pytest.mark.asyncio
async def test_a_new_battle_goes_to_its_player_and_the_lobby_to_everyone():
    room = FakeRoom()
    me, other = FakeConn(room, 1), FakeConn(room, 2)
    win, _ = window(room)
    run = await solo(win, me)
    assert sent(me, "battle")[0]["id"] == run.id and sent(me, "battle")[0]["you"] == 1
    assert not sent(other, "battle")
    await win.tick()
    assert sent(other, "lobby")[-1]["battles"][0]["id"] == run.id


@pytest.mark.asyncio
async def test_each_tick_runs_three_steps_and_sends_an_update():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, _ = window(room)
    run = await solo(win, me)
    await win.tick()
    await win.tick()
    updates = sent(me, "u")
    assert [u["step"] for u in updates] == [STEPS, 2 * STEPS] and run.battle.step == 2 * STEPS
    assert len(updates[0]["r"]) == 2


@pytest.mark.asyncio
async def test_a_result_is_reported_once_and_the_battle_ends_after_its_banner():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, results = window(room)
    run = await solo(win, me)
    enemy = run.battle.robots[1]
    run.battle.hurt(enemy, enemy.health, team=1)
    ticks = 0
    while run.id in win.runs:
        await win.tick()
        ticks += 1
    assert results == [run]
    assert ticks == -(-(engine.BANNER_STEPS + engine.FADE_STEPS) // STEPS)
    assert sent(me, "over") == [{"id": run.id, "next": "shop"}]


@pytest.mark.asyncio
async def test_the_next_screen_follows_the_kind_of_battle():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, _ = window(room)
    run = await solo(win, me, kind="challenge")
    run.battle.finish(1)
    for _ in range(40):
        await win.tick()
    assert sent(me, "over")[-1]["next"] == "challenges"
    run = await solo(win, me)
    run.beats_game = True
    run.battle.finish(1)
    for _ in range(40):
        await win.tick()
    assert sent(me, "over")[-1]["next"] == "wingame"


@pytest.mark.asyncio
async def test_watchers_see_the_battle_but_cant_order():
    room = FakeRoom()
    me, fan = FakeConn(room, 1), FakeConn(room, 2)
    win, _ = window(room)
    run = await solo(win, me)
    await win.watch(fan, run.id)
    assert sent(fan, "battle")[0]["you"] is None
    await win.tick()
    assert sent(fan, "u")
    win.order(fan, [1, 300, 100])
    assert run.battle.robots[0].order == ("standard",)
    win.order(me, [1, 300, 100])
    assert run.battle.robots[0].order[0] == "goto"
    win.unwatch(fan)
    count = len(sent(fan, "u"))
    await win.tick()
    assert len(sent(fan, "u")) == count


@pytest.mark.asyncio
async def test_bad_orders_and_bad_watch_ids_are_ignored():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, _ = window(room)
    run = await solo(win, me)
    for value in (None, [1, 2], [True, 3, 4], [1, "x", 4], [1, float("nan"), 4], [2, 300, 100]):
        win.order(me, value)
    assert run.battle.robots[0].order == ("standard",)
    await win.watch(me, run.id)
    await win.watch(me, "nope")
    await win.watch(me, 5)
    assert run.watchers == []


@pytest.mark.asyncio
async def test_orders_far_off_the_stage_are_ignored():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, _ = window(room)
    run = await solo(win, me)
    for value in ([1, 1e308, 100], [1, 300, -1e308], [1, 10_001, 100], [1, 300, -10_001], [1, 10**400, 5]):
        win.order(me, value)
    assert run.battle.robots[0].order == ("standard",)
    win.order(me, [1, 10_000, 100])
    assert run.battle.robots[0].order[0] == "goto"


@pytest.mark.asyncio
async def test_ids_never_repeat_across_windows():
    first, second = window()[0], window()[0]
    one, two = FakeConn(first.room, 1), FakeConn(second.room, 2)
    ids = [(await solo(first, one)).id, (await solo(second, two)).id]
    ids += [first.open_fight(1, "A", "A", 1, None).id, second.open_fight(2, "B", "B", 1, None).id]
    assert len(set(ids)) == 4


@pytest.mark.asyncio
async def test_a_page_joining_mid_battle_gets_the_whole_battle():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, _ = window(room)
    run = await solo(win, me)
    enemy = run.battle.robots[1]
    run.battle.hurt(enemy, enemy.health, team=1)
    await win.tick()
    again = FakeConn(room, 1)
    await win.join(again)
    full = sent(again, "battle")[0]
    assert full["id"] == run.id and full["step"] == run.battle.step and full["ended"] == 0
    assert full["winner"] == 1 and full["flames"][0][0] == enemy.id and len(full["robots"]) == 2
    assert sent(again, "lobby")


@pytest.mark.asyncio
async def test_a_stalled_battle_nobody_is_watching_is_stopped():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, results = window(room)
    run = await solo(win, me)
    me.drop()
    run.battle.step = engine.DRAW_STEPS
    await win.tick()
    assert run.id not in win.runs and results == []


@pytest.mark.asyncio
async def test_the_window_lives_while_people_or_battles_are_in_it():
    room = FakeRoom()
    me = FakeConn(room, 1)
    win, _ = window(room)
    assert win.alive()
    run = await solo(win, me)
    me.drop()
    assert win.alive()
    del win.runs[run.id]
    assert not win.alive()


# ---------- Who's here ----------


@pytest.mark.asyncio
async def test_a_battle_comes_with_its_watchers_once_each():
    room = FakeRoom()
    me, fan, again = FakeConn(room, 1), FakeConn(room, 2), FakeConn(room, 2)
    win, _ = window(room)
    run = await solo(win, me)
    assert sent(me, "battle")[0]["watchers"] == []
    await win.watch(fan, run.id)
    await win.watch(again, run.id)
    face = {"id": "2", "name": "Player 2", "avatar": "https://cdn.discordapp.com/avatars/2/a.png"}
    # The same person on two devices is one face
    assert sent(again, "battle")[0]["watchers"] == [face]


@pytest.mark.asyncio
async def test_watchers_go_to_everyone_seeing_the_battle_only_when_they_change():
    room = FakeRoom()
    me, fan, other = FakeConn(room, 1), FakeConn(room, 2), FakeConn(room, 3)
    win, _ = window(room)
    run = await solo(win, me)
    await win.tick()
    # Nobody watching yet: nothing changed, so nothing is sent
    assert sent(me, "watchers") == []
    await win.watch(fan, run.id)
    await win.tick()
    await win.tick()
    (told,) = sent(me, "watchers")
    assert told["id"] == run.id and [face["name"] for face in told["people"]] == ["Player 2"]
    assert sent(fan, "watchers") == [told]
    assert sent(other, "watchers") == []
    win.unwatch(fan)
    await win.tick()
    assert sent(me, "watchers")[-1] == {"id": run.id, "people": []}
    assert len(sent(me, "watchers")) == 2


@pytest.mark.asyncio
async def test_a_watcher_closing_their_page_leaves_the_faces():
    room = FakeRoom()
    me, fan = FakeConn(room, 1), FakeConn(room, 2)
    win, _ = window(room)
    run = await solo(win, me)
    await win.watch(fan, run.id)
    await win.tick()
    fan.drop()
    win.leave(fan)
    await win.tick()
    assert sent(me, "watchers")[-1]["people"] == []


@pytest.mark.asyncio
async def test_joining_a_friend_in_a_battle_watches_it():
    room = FakeRoom()
    friend = FakeConn(room, 1)
    win, _ = window(room)
    run = await solo(win, friend)
    me = FakeConn(room, 2)
    await win.join(me, follow=1)
    assert sent(me, "battle")[0]["id"] == run.id and sent(me, "battle")[0]["you"] is None
    assert run.watchers == [me]


@pytest.mark.asyncio
async def test_joining_a_friend_who_watches_watches_the_same_battle():
    room = FakeRoom()
    player, friend = FakeConn(room, 1), FakeConn(room, 3)
    win, _ = window(room)
    run = await solo(win, player)
    await win.watch(friend, run.id)
    me = FakeConn(room, 2)
    await win.join(me, follow=3)
    assert sent(me, "battle")[0]["id"] == run.id
    assert me in run.watchers


@pytest.mark.asyncio
async def test_joining_a_friend_with_an_open_fight_goes_to_pvp():
    room = FakeRoom()
    FakeConn(room, 1)
    win, _ = window(room)
    win.open_fight(1, "Player 1", "Global 1", 1, None)
    me = FakeConn(room, 2)
    await win.join(me, follow=1)
    assert sent(me, "follow") == ["pvp"]
    assert sent(me, "battle") == []


@pytest.mark.asyncio
async def test_joining_a_friend_doing_nothing_together_or_your_own_battle_follows_nobody():
    room = FakeRoom()
    FakeConn(room, 1)
    win, _ = window(room)
    me = FakeConn(room, 2)
    await win.join(me, follow=1)
    assert sent(me, "follow") == [] and sent(me, "battle") == []
    # Your own battle comes first: a Join never takes you out of it
    friend = FakeConn(room, 3)
    theirs = await solo(win, friend)
    mine = await solo(win, me)
    again = FakeConn(room, 2)
    await win.join(again, follow=3)
    assert [b["id"] for b in sent(again, "battle")] == [mine.id]
    assert theirs.watchers == []
