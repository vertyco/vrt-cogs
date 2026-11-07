"""Hold'em's session: free practice against CPUs, real hands for credits, and who may see which cards"""

import asyncio
import json

import pytest

from vegas.common.games.holdem import Action
from vegas.common.games.poker import describe
from vegas.common.holdem_table import PRACTICE_BLINDS
from vegas.common.sockets import Sockets
from vegas.tests.fakes import FakeConn
from vegas.tests.tables_kit import ScriptedDeck, autoplay, hand_over, keep_playing, open_turn, time_out, until

CALL, CHECK, FOLD = {"move": "call"}, {"move": "check"}, {"move": "fold"}
BIG = 20  # the default Max of 2,000 makes blinds of 10 and 20
SUITS = {"s": "spades", "h": "hearts", "d": "diamonds", "c": "clubs"}


def cards(text: str) -> list[tuple[str, str]]:
    """Cards written short, like "As 10h" """
    return [(word[:-1], SUITS[word[-1]]) for word in text.split()]


# Hand 1 is always practice (whoever sits first is alone): 4 seats take 8 cards, all clubs
PRACTICE = cards("2c 3c 4c 5c 6c 7c 8c 9c")
# Heads-up, dealt from the small blind (Ann, seat 4): Ann's aces against Sam's kings, then the board
HEADS_UP = cards("As Ks Ah Kh 2d 7d 9h Jd 4s")
# Three-handed, dealt from the small blind (Bob, seat 5), then Sam (0) and Ann (4), then the board
THREE_WAY = cards("As Ks Qs Ah Kh Qh 2d 7d 9h Jd 4s")


def calls(spot, rng):
    """A CPU that checks when it can and calls everything else"""
    return Action("check") if spot.legal.check else Action("call")


def folds(spot, rng):
    """A CPU that checks when it can and folds to any bet"""
    return Action("check") if spot.legal.check else Action("fold")


def deal_from(table, *scripts):
    """Each hand draws from the next script; after the last, from a shuffled deck"""
    queue = [ScriptedDeck(script) for script in scripts]
    table.new_deck = lambda: queue.pop(0) if queue else ScriptedDeck([])


def hands_of(conn) -> list[list[dict]]:
    """The events of each hand the connection saw, split at the button event that starts a hand"""
    hands = []
    for event in conn.of("event"):
        if event["kind"] == "button":
            hands.append([])
        elif hands:
            hands[-1].append(event)
    return hands


def state_after(conn, **match) -> dict:
    """The first table state sent after the first event with these fields, like kind="win" """
    found = next(
        i
        for i, m in enumerate(conn.sent)
        if m.get("t") == "event" and all(m.get(key) == value for key, value in match.items())
    )
    return next(m for m in conn.sent[found:] if m.get("t") == "table")


def shows_chips(state: dict) -> bool:
    return any(seat is not None and (seat["cards"] or seat["bet"]) for seat in state["seats"])


def early_states(conn) -> list[dict]:
    """Table states that showed blinds or cards at a seat before that hand's last card was pitched"""
    events = [(i, m["kind"]) for i, m in enumerate(conn.sent) if m.get("t") == "event"]
    ends = [i for i, kind in events if kind == "win"] + [len(conn.sent)]
    pitches = [i for i, kind in events if kind == "pitch"]
    early, start = [], 0
    for end in ends:
        dealt = [i for i in pitches if start <= i < end]
        if dealt:
            early += [m for m in conn.sent[start : dealt[-1]] if m.get("t") == "table" and shows_chips(m)]
        start = end
    return early


def acts(events, seat: int) -> list[str]:
    return [e["move"] for e in events if e["kind"] == "act" and e["seat"] == seat and e["move"] != "blind"]


def played(conn, seat: int, move: str, hand: int = 0) -> bool:
    hands = hands_of(conn)
    return len(hands) > hand and move in acts(hands[hand], seat)


async def balance(host, conn) -> int:
    return await host.money.bank.balance(conn.ctx.author)


async def first_real_hand(seat, *scripts, cpu=folds):
    """Sam buys in at seat 0 and so practices hand 1 alone with 3 CPUs. Ann buys in at seat 4 while it runs and Sam
    folds it, so hand 2 is the first real hand: heads-up, Ann on the button and small blind, Sam the big blind"""
    host, floor, table, (sam, ann) = await seat("holdem", 7, 8)
    deal_from(table, *scripts)
    table.choose = cpu
    await table.buy_in(sam, {"seat": 0, "amount": 1000, "post": False})
    await until(lambda: 7 in table.decisions)
    await table.sit(ann, 4)
    assert ann.last("notice")["text"] == "Buy in to sit."
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    assert ann.last("me")["balance"] == 0 and sam.last("me")["balance"] == 0
    await autoplay(table, sam, [FOLD])
    await until(lambda: table.hand_no == 2)
    return host, floor, table, sam, ann


@pytest.mark.asyncio
async def test_alone_a_free_seat_brings_3_cpus_and_practice_hands_start(seat):
    host, floor, table, (sam,) = await seat("holdem", 7)
    table.choose = calls
    await table.sit(sam, 2)
    await until(lambda: table.hand_no >= 1 and 7 in table.decisions)
    assert table.mode == "practice"
    cpus = [s for s in table.seats if s is not None and s.cpu]
    assert [s.number for s in cpus] == [0, 1, 3] and all(s.name.startswith("CPU ") for s in cpus)
    assert len({s.name for s in cpus}) == 3 and all(s.id < 0 for s in cpus)
    assert await balance(host, sam) == 1000 and table.seat_of(7).real == 0
    assert all(s.play == PRACTICE_BLINDS * BIG for s in table.seats if s is not None)
    assert sorted(e["seat"] for e in sam.of("event") if e["kind"] == "seat") == [0, 1, 2, 3]
    state = sam.last("table")
    assert state["mode"] == "practice" and state["hand"] == 1 and state["turn"] == 2 and state["waiting"] == ["7"]
    assert state["stakes"] == {"small": 10, "big": BIG, "min": 400, "max": 2000, "cut": 5.0}
    assert [s["cpu"] for s in state["seats"][:4]] == [True, True, False, True] and state["seats"][4] is None
    assert state["seats"][0]["avatar"] is None and state["seats"][2]["avatar"]


@pytest.mark.asyncio
async def test_two_buy_ins_play_a_real_hand_and_chips_are_kept_exactly(seat):
    host, floor, table, sam, ann = await first_real_hand(seat, PRACTICE, HEADS_UP)
    assert table.mode == "real" and not any(s is not None and s.cpu for s in table.seats)
    await asyncio.gather(autoplay(table, ann, [CALL, CHECK, CHECK, CHECK]), autoplay(table, sam, [CHECK] * 4))
    await hand_over(table, 2)
    win = hands_of(sam)[1][-1]
    assert win["kind"] == "win"
    total = await balance(host, sam) + await balance(host, ann) + sum(s.real for s in table.seats if s is not None)
    assert total + win["cut"] == 2000
    # The pot of 40 saw the flop: 5% is a cut of 2, and Ann's aces take the other 38
    assert win["cut"] == 2 and win["big"] is False
    assert win["awards"] == [{"amount": 38, "winners": [4], "shares": {"4": 38}}]
    assert sorted(map(tuple, win["best"]["4"])) == sorted(cards("As Ah Jd 9h 7d")) and list(win["best"]) == ["4"]
    assert (table.seat_of(7).real, table.seat_of(8).real) == (980, 1018)
    scope = await floor.scope()
    assert (await host.store.stacked(scope, 7), await host.store.stacked(scope, 8)) == (980, 1018)


@pytest.mark.asyncio
async def test_nobody_else_ever_receives_your_hole_cards(seat):
    host, floor, table, (sam, ann, bob, dan) = await seat("holdem", 7, 8, 9, 10)
    deal_from(table, PRACTICE, THREE_WAY)
    table.choose = folds
    await table.buy_in(sam, {"seat": 0, "amount": 1000, "post": False})
    await until(lambda: 7 in table.decisions)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    await table.buy_in(bob, {"seat": 5, "amount": 1000, "post": False})
    await asyncio.gather(
        autoplay(table, sam, [FOLD] + [CHECK] * 4),
        autoplay(table, ann, [CALL] + [CHECK] * 3),
        autoplay(table, bob, [CALL] + [CHECK] * 3),
    )
    await hand_over(table, 2)
    holes = {7: cards("Ks Kh"), 8: cards("Qs Qh"), 9: cards("As Ah")}
    for conn in (sam, ann, bob, dan):
        owner = conn.ctx.author.id
        assert owner == 10 or holes[owner] in [list(map(tuple, h["cards"])) for h in conn.of("hole")]
        shown = next(i for i, m in enumerate(conn.sent) if m.get("t") == "event" and m["kind"] == "show")
        seen = [json.dumps(message) for message in conn.sent[:shown]]
        secrets = [card for user_id, hole in holes.items() if user_id != owner for card in hole]
        assert len(secrets) == (6 if owner == 10 else 4)
        for secret in secrets:
            assert not [text for text in seen if json.dumps(list(secret)) in text], (owner, secret)
    assert not dan.of("hole") and not dan.of("ask")


@pytest.mark.asyncio
async def test_a_reconnect_gets_its_hole_cards_and_buttons_back(seat):
    host, floor, table, (sam,) = await seat("holdem", 7)
    table.choose = calls
    await table.sit(sam, 2)
    await until(lambda: 7 in table.decisions)
    await floor.depart(sam)
    sam.sent.clear()
    await floor.arrive(sam)
    await floor.enter(sam, "holdem")
    hole = sam.last("hole")
    assert hole["cards"] == [list(card) for card in table.holes[2]] and hole["hand"] == 1 and hole["name"]
    assert sam.last("ask") == {
        "t": "ask",
        "game": "holdem",
        "moves": ["check", "raise"],
        "call": 0,
        "min_to": 40,
        "max_to": 2000,
        "pot": 80,
        "bet": BIG,
    }
    assert sam.last("table")["seats"][2]["cards"] == 2 and "hole" not in json.dumps(sam.last("table"))
    await table.move(sam, CHECK)
    # The messages from before the reconnect are gone, button event included, so look at every event left
    await until(lambda: "check" in acts(sam.of("event"), 2))


@pytest.mark.asyncio
async def test_a_timeout_checks_when_free_and_folds_when_facing_a_bet(seat):
    host, floor, table, (sam,) = await seat("holdem", 7)
    table.choose = calls
    await table.sit(sam, 2)
    # Hand 1: Sam is the big blind and everyone calls, so checking is free. His clock runs out before the flop and on
    # the turn; he checks the flop and the river himself, so two timeouts in a row never stand him up.
    # Hand 2: Sam is the small blind, facing the big blind, and his clock runs out
    turns = [(1, "preflop", True), (1, "flop", False), (1, "turn", True), (1, "river", False), (2, "preflop", True)]
    for number, street, timed_out in turns:
        await until(lambda: table.hand_no == number and table.street == street and open_turn(table, 7, None))
        if timed_out:
            time_out(table, 7)
        else:
            await table.move(sam, CHECK)
    await until(lambda: played(sam, 2, "fold", hand=1))
    first, second = hands_of(sam)[:2]
    assert acts(first, 2) == ["check"] * 4
    assert acts(second, 2) == ["fold"] and table.seat_of(7).timeouts == 1


@pytest.mark.asyncio
async def test_a_bad_or_out_of_turn_move_is_ignored(seat):
    host, floor, table, (sam, ann) = await seat("holdem", 7, 8)
    table.choose = calls
    await table.sit(sam, 2)
    await until(lambda: 7 in table.decisions)
    future, deadline = table.decisions[7], table.deadline
    bad = [
        {"move": "raise", "amount": "x"},
        {"move": "raise", "amount": True},
        {"move": "raise", "amount": -5},
        {"move": "raise", "amount": 39},
        {"move": "raise", "amount": 2001},
        {"move": "raise", "amount": 40.0},
        {"move": "raise"},
        {"move": "double"},
        {"move": "fold"},
        {"move": "call"},
        {"move": ["check"]},
    ]
    for data in bad:
        await table.move(sam, data)
        await Sockets.dispatch(host, floor, sam, {"t": "move", **data})
    await table.move(ann, CHECK)
    await Sockets.dispatch(host, floor, ann, {"t": "move", "move": "check"})
    assert not future.done() and table.decisions[7] is future and table.deadline == deadline
    assert table.hand.to_act == 2 and table.hand.players[2].bet == BIG
    await Sockets.dispatch(host, floor, sam, {"t": "bet", "amount": 100})
    await Sockets.dispatch(host, floor, sam, {"t": "go"})
    assert await balance(host, sam) == 1000 and not table.bets
    assert await host.store.stacks() == [] and not sam.of("result")
    await Sockets.dispatch(host, floor, sam, {"t": "move", "move": "raise", "amount": 40})
    await until(lambda: played(sam, 2, "raise"))
    raised = [e for e in hands_of(sam)[0] if e["kind"] == "act" and e["seat"] == 2][-1]
    assert (raised["amount"], raised["stack"]) == (40, 1960)


@pytest.mark.asyncio
async def test_one_person_on_two_devices_gets_one_seat_and_sees_their_cards_on_both(seat):
    host, floor, table, (pc,) = await seat("holdem", 7)
    phone = FakeConn(floor.room, pc.ctx.author, floor.guild)
    await floor.arrive(phone)
    await floor.enter(phone, "holdem")
    table.choose = calls
    await table.sit(pc, 2)
    await table.sit(phone, 4)
    await table.buy_in(phone, {"seat": 5, "amount": 1000, "post": False})
    await until(lambda: 7 in table.decisions)
    assert [s.number for s in table.seats if s is not None and not s.cpu] == [2]
    assert await balance(host, pc) == 1000 and await host.store.stacks() == []
    mine = [list(card) for card in table.holes[2]]
    assert pc.last("hole")["cards"] == phone.last("hole")["cards"] == mine
    assert pc.last("ask") == phone.last("ask")
    await table.move(phone, CHECK)
    await until(lambda: played(pc, 2, "check") and played(phone, 2, "check"))


@pytest.mark.asyncio
async def test_all_in_before_the_river_shows_hands_then_runs_out_the_board(seat):
    host, floor, table, (sam,) = await seat("holdem", 7)
    table.choose = calls
    await table.sit(sam, 2)
    await until(lambda: 7 in table.decisions)
    await table.move(sam, {"move": "raise", "amount": 2000})
    await hand_over(table, 1)
    events = hands_of(sam)[0]
    last_act = max(i for i, e in enumerate(events) if e["kind"] == "act")
    assert [e["kind"] for e in events[last_act + 1 :]] == ["show"] + ["runout"] * 5 + ["win"]
    assert sorted(events[last_act + 1]["hands"]) == ["0", "1", "2", "3"]
    board = [tuple(e["card"]) for e in events if e["kind"] == "runout"]
    # Sam's hand name follows the board one card at a time, and the shown hands end with their final names
    holes = [h for h in sam.of("hole") if h["hand"] == 1]
    mine = [tuple(card) for card in holes[0]["cards"]]
    assert [h["name"] for h in holes] == [describe(mine + board[:count]) for count in range(6)]
    shown = state_after(sam, kind="win")["shown"]
    assert sorted(shown) == ["0", "1", "2", "3"] and shown["2"]["name"] == describe(mine + board)
    win = events[-1]
    assert win["cut"] == 0 and win["big"] is True
    assert sum(sum(award["shares"].values()) for award in win["awards"]) == 4 * PRACTICE_BLINDS * BIG


async def shove(table, conn) -> None:
    """Answers every turn this player gets with all their chips, or a call or check when no raise is left, until
    cancelled"""
    user_id = conn.ctx.author.id
    answered = None
    while True:
        await until(lambda: open_turn(table, user_id, answered), 3600)
        answered = table.decisions[user_id]
        if "raise" in table.allowed[user_id]:
            move = {"move": "raise", "amount": table.hand.legal(table.seat_of(user_id).number).max_to}
        else:
            move = CALL if "call" in table.allowed[user_id] else CHECK
        await table.move(conn, move)


@pytest.mark.asyncio
async def test_a_short_all_in_shows_its_side_pot_before_the_board_runs_out(seat):
    host, floor, table, (sam, ann, bob) = await seat("holdem", 7, 8, 9)
    deal_from(table, PRACTICE)
    table.choose = folds
    await table.buy_in(sam, {"seat": 0, "amount": 1000, "post": False})
    await until(lambda: 7 in table.decisions)
    await table.buy_in(ann, {"seat": 4, "amount": 1000, "post": False})
    await table.buy_in(bob, {"seat": 5, "amount": 400, "post": False})
    await autoplay(table, sam, [FOLD])
    await until(lambda: table.hand_no == 2)
    # Everyone goes all in before the flop: Bob's 400 makes a main pot all three can win, and a side pot of the 600 more
    # Sam and Ann each put in
    players = [asyncio.create_task(shove(table, conn)) for conn in (sam, ann, bob)]
    try:
        await hand_over(table, 2)
    finally:
        for player in players:
            player.cancel()
    show = next(e for e in hands_of(sam)[1] if e["kind"] == "show")
    assert show["pots"] == [1200, 1200]
    # From the hands turning up on, the pots hold every chip and no bet is left in front of a seat
    state = state_after(sam, kind="show")
    assert state["pots"] == [1200, 1200] and all(s is None or s["bet"] == 0 for s in state["seats"])


@pytest.mark.asyncio
async def test_practice_hands_take_no_cut(seat):
    host, floor, table, (sam,) = await seat("holdem", 7)
    table.choose = calls
    await table.sit(sam, 2)
    playing = asyncio.create_task(keep_playing(table, sam))
    await hand_over(table, 1)
    playing.cancel()
    win = hands_of(sam)[0][-1]
    # Everyone put in 20 and checked to the river: a pot of 80 that saw the flop (a real hand would cut 4)
    assert win["kind"] == "win" and win["cut"] == 0
    assert sum(sum(award["shares"].values()) for award in win["awards"]) == 4 * BIG


@pytest.mark.asyncio
async def test_the_table_shows_blinds_and_cards_only_after_they_are_dealt(seat):
    host, floor, table, (sam, ann) = await seat("holdem", 7, 8)
    table.choose = calls
    await table.sit(sam, 2)
    playing = asyncio.create_task(keep_playing(table, sam))
    await hand_over(table, 2)
    playing.cancel()
    for conn in (sam, ann):
        assert early_states(conn) == []
        # Once hand 1's last card has flown, the next state shows the blinds and the face-down cards
        win = next(i for i, m in enumerate(conn.sent) if m.get("t") == "event" and m["kind"] == "win")
        pitched = max(i for i, m in enumerate(conn.sent[:win]) if m.get("t") == "event" and m["kind"] == "pitch")
        dealt = next(m for m in conn.sent[pitched:] if m.get("t") == "table")
        assert dealt["seats"][2]["cards"] == 2 and dealt["seats"][2]["bet"] == BIG


@pytest.mark.asyncio
async def test_an_uncalled_bet_comes_back_and_its_tag_follows(seat):
    host, floor, table, sam, ann = await first_real_hand(seat, PRACTICE, HEADS_UP)
    await autoplay(table, ann, [{"move": "raise", "amount": 200}])
    await autoplay(table, sam, [FOLD])
    await hand_over(table, 2)
    # Nobody called Ann's raise to 200, so all but the 20 Sam's big blind matched comes back to her
    returned = [e for e in hands_of(ann)[1] if e["kind"] == "act" and e["move"] == "return"]
    assert returned == [
        {"t": "event", "game": "holdem", "kind": "act", "seat": 4, "move": "return", "amount": BIG, "stack": 1000 - BIG}
    ]
    # Every table after keeps how much came back, so the seat's tag can say "Got 180 back"
    last = {"move": "return", "amount": BIG, "back": 200 - BIG}
    assert state_after(ann, kind="act", move="return", seat=4)["seats"][4]["last"] == last


@pytest.mark.asyncio
async def test_real_hands_count_in_stats_and_practice_hands_do_not(seat):
    host, floor, table, sam, ann = await first_real_hand(seat, PRACTICE, HEADS_UP)
    scope = await floor.scope()
    rows = [await host.store.player_game(scope, uid, "holdem") for uid in (7, 8)]
    assert [(row.played, row.won) for row in rows] == [(0, 0), (0, 0)]
    await asyncio.gather(autoplay(table, ann, [CALL, CHECK, CHECK, CHECK]), autoplay(table, sam, [CHECK] * 4))
    await hand_over(table, 2)
    rows = [await host.store.player_game(scope, uid, "holdem") for uid in (7, 8)]
    assert [(row.played, row.won) for row in rows] == [(1, 0), (1, 1)]


@pytest.mark.asyncio
async def test_the_stack_row_holds_the_hand_start_amount_during_a_hand(seat):
    host, floor, table, sam, ann = await first_real_hand(seat, PRACTICE, HEADS_UP)
    scope = await floor.scope()

    async def rows():
        return await host.store.stacked(scope, 7), await host.store.stacked(scope, 8)

    await autoplay(table, ann, [{"move": "raise", "amount": 200}])
    await until(lambda: 7 in table.decisions)
    assert table.hand.players[4].bet == 200 and await rows() == (1000, 1000)
    await autoplay(table, sam, [FOLD])
    await hand_over(table, 2)
    # Ann's uncalled 180 came back and she took Sam's big blind; no flop, so no cut
    assert await rows() == (980, 1020)
    await until(lambda: table.hand_no == 3 and 7 in table.decisions)
    assert table.hand.players[0].bet == 10 and table.hand.players[4].bet == BIG
    assert await rows() == (980, 1020)


@pytest.mark.asyncio
async def test_cpus_never_touch_real_credits(seat, monkeypatch):
    host, floor, table, (sam,) = await seat("holdem", 7)
    moved = []
    bank = host.money.bank

    async def withdraw(who, amount):
        moved.append(("withdraw", who.id, amount))

    async def deposit(who, amount):
        moved.append(("deposit", who.id, amount))
        return 0

    monkeypatch.setattr(bank, "withdraw", withdraw)
    monkeypatch.setattr(bank, "deposit", deposit)
    await table.sit(sam, 2)
    playing = asyncio.create_task(keep_playing(table, sam))
    await hand_over(table, 2, seconds=30)
    playing.cancel()
    assert table.mode == "practice" and moved == [] and await balance(host, sam) == 1000
    assert await host.store.stacks() == []
    row = await host.store.player_game(await floor.scope(), 7, "holdem")
    assert (row.played, row.won) == (0, 0)
    assert all(s.real == 0 for s in table.seats if s is not None)


def table_before(conn, kind: str) -> dict:
    """The last table state sent before the first event of this kind"""
    found = next(i for i, m in enumerate(conn.sent) if m.get("t") == "event" and m["kind"] == kind)
    return next(m for m in reversed(conn.sent[:found]) if m.get("t") == "table")


@pytest.mark.asyncio
async def test_the_first_real_game_shows_credits_before_the_cpus_leave(seat):
    host, floor, table, sam, ann = await first_real_hand(seat, PRACTICE, HEADS_UP)
    # The table that goes out as the CPUs fade away is already the real game: no practice chips for a moment
    state = table_before(ann, "unseat")
    assert state["mode"] == "real"
    assert [s and (s["id"], s["stack"]) for s in state["seats"]] == [("7", 1000), None, None, None, ("8", 1000), None]


@pytest.mark.asyncio
async def test_a_buy_in_at_a_quiet_table_shows_the_credits_bought(seat):
    host, floor, table, (sam,) = await seat("holdem", 7)
    table.choose = calls
    await table.buy_in(sam, {"seat": 0, "amount": 1000, "post": False})
    # Before practice starts the seat shows what Sam bought in with, not the practice chips
    first = next(m for m in sam.sent if m.get("t") == "table" and m["seats"][0] is not None)
    assert first["mode"] == "idle" and first["seats"][0]["stack"] == 1000
