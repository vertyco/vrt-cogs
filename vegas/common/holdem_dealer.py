"""One Hold'em hand, from the button to the results: the deal, each betting round with its human and CPU turns, the
shared cards, and the showdown. The table keeps the seats and decides who may see which cards"""

import asyncio
import logging
import typing as t

from .games.cards import Deck
from .games.holdem import Action, Hand, Positions, positions, settle
from .games.holdem_cpu import Spot
from .games.poker import best_hand

if t.TYPE_CHECKING:
    from .holdem_table import HoldemTable

log = logging.getLogger("red.vrt.vegas.holdem")

CPU_THINK = (1.0, 2.5)  # seconds a CPU takes over a move, so it feels like a person
STREET_CARDS = {"flop": 3, "turn": 1, "river": 1}
TIMEOUTS_TO_STAND = 2  # turns in a row a player lets run out before they stand up when the hand ends


def fallback(hand: Hand, seat: int) -> Action:
    """What a player who doesn't answer does: check when it's free, otherwise fold"""
    return Action("check") if hand.legal(seat).check else Action("fold")


async def play_hand(table: "HoldemTable") -> None:
    small, big = table.limits[0], table.limits[1]
    # Practice chips leave nothing to drain from the economy, so only real hands are cut
    cut = table.limits[4] if table.mode == "real" else 0.0
    # Pages see the last hand cleared away now. The next state comes only after the blinds and cards have flown,
    # so the page never shows them before their animations
    await table.push()
    # No buy-in, top-up or stand lands between reading the seats and dealing them in
    async with table.lock:
        active, waiting = table.lineup()
        spots = positions(active, waiting, table.button)
        if spots is None:
            return
        stacks = {number: table.chips(table.seats[number]) for number in spots.dealt}
        hand = begin(table, spots, stacks, small, big)
    deck = table.new_deck()
    await table.event("button", seat=spots.button)
    await post_blinds(table, hand, stacks)
    await deal(table, hand, deck)
    await play_streets(table, hand, deck)
    await finish(table, hand, deck, cut)


def begin(table: "HoldemTable", spots: Positions, stacks: dict[int, int], small: int, big: int) -> Hand:
    """A new hand on the table, with the hand-start credits kept in case it never finishes"""
    hand = Hand(stacks, spots, small, big, posts_for(table, spots))
    table.hand_no += 1
    table.round = table.hand_no
    table.phase = "playing"
    table.button = spots.button
    table.hand, table.street, table.turn = hand, hand.street, None
    table.board, table.holes, table.shown, table.last, table.pots = [], {}, {}, {}, []
    table.start = {number: table.seats[number].real for number in spots.dealt} if table.mode == "real" else {}
    return hand


def posts_for(table: "HoldemTable", spots: Positions) -> set[int]:
    """Real-game seats that chose to pay a big blind to play now, outside the blinds. Everyone dealt in has joined,
    so their choice to post or wait is used up"""
    posts = set()
    if table.mode == "real":
        posts = {n for n in spots.dealt if table.seats[n].post and n not in (spots.small, spots.big)}
    for number in spots.dealt:
        table.seats[number].post = table.seats[number].waiting = False
    return posts


async def post_blinds(table: "HoldemTable", hand: Hand, stacks: dict[int, int]) -> None:
    for seat, kind, chips in hand.posted:
        move = "post" if kind == "post" else "blind"
        table.last[seat] = {"move": move, "amount": chips}
        await table.event("act", seat=seat, move=move, amount=chips, stack=stacks[seat] - chips)


async def deal(table: "HoldemTable", hand: Hand, deck: Deck) -> None:
    """Two cards each, one at a time from the small blind clockwise. Each person sees their own before the cards fly"""
    dealt = hand.spots.dealt
    first = dealt.index(hand.spots.small)
    order = dealt[first:] + dealt[:first]
    for seat in order * 2:
        table.holes.setdefault(seat, []).append(deck.draw())
    await table.send_holes()
    for seat in order * 2:
        await table.event("pitch", seat=seat)


async def play_streets(table: "HoldemTable", hand: Hand, deck: Deck) -> None:
    """Betting rounds with the shared cards between them, until one player is left, the river's betting is done, or
    nobody can bet any more"""
    while True:
        await betting_round(table, hand)
        await give_back(table, hand)
        if len(hand.contenders) < 2 or hand.betting_done or hand.street == "river":
            return
        pots = [pot.amount for pot in hand.pots()]
        if any(player.bet for player in hand.players.values()):
            await table.event("sweep", pots=pots)
        next_street(table, hand, pots)
        table.last = {}
        await deal_street(table, hand, deck)


def next_street(table: "HoldemTable", hand: Hand, pots: list[int]) -> None:
    """The finished round's bets join the pots"""
    hand.next_street()
    table.street = hand.street
    table.pots = pots


async def deal_street(table: "HoldemTable", hand: Hand, deck: Deck) -> None:
    cards = [deck.draw() for count in range(STREET_CARDS[hand.street])]
    table.board.extend(cards)
    if len(cards) == 3:
        await table.event("flop", cards=[list(card) for card in cards])
    else:
        await table.event("street", card=list(cards[0]))
    await table.board_changed()


async def betting_round(table: "HoldemTable", hand: Hand) -> None:
    while (seat := hand.to_act) is not None:
        table.turn = seat
        action = await take_turn(table, hand, seat)
        move = apply(hand, seat, action)
        player = hand.players[seat]
        table.last[seat] = {"move": move, "amount": player.bet}
        await table.event("act", seat=seat, move=move, amount=player.bet, stack=player.stack)
    table.turn = None


async def take_turn(table: "HoldemTable", hand: Hand, number: int) -> Action:
    default = fallback(hand, number)
    seat = table.seats[number]
    # A player who stood up or left plays the default at once: a free check, otherwise a fold
    if seat is None or seat.leaving:
        return default
    if seat.cpu:
        return await cpu_turn(table, hand, number, default)
    user_id = seat.member.id
    # A player away in their leave grace is asked like anyone else, on the same clock: they may be reconnecting
    here = table.is_here(user_id)
    action = (await table.decide([user_id], hand.legal(number).moves(), default, table.times["decision"]))[user_id]
    # A turn that ran out of time comes back as the default itself. Any move sent starts the count again. A turn spent
    # away from start to end is no strike (the seat grace stands up anyone who doesn't come back), but stepping out
    # just before the clock runs out still counts
    if action is not default:
        seat.timeouts = 0
    elif here or table.is_here(user_id):
        seat.timeouts += 1
        seat.leaving = seat.leaving or seat.timeouts >= TIMEOUTS_TO_STAND
    return action


async def cpu_turn(table: "HoldemTable", hand: Hand, number: int, default: Action) -> Action:
    """A CPU thinks for a moment like a person would. Its choice runs off the bot's main loop"""
    rng = table.cog.rng
    await table.push()
    await table.pause(rng.uniform(*CPU_THINK))
    spot = Spot(
        hole=tuple(table.holes[number]),
        board=tuple(table.board),
        legal=hand.legal(number),
        pot=hand.pot_total,
        big=hand.big,
        opponents=len(hand.contenders) - 1,
        street=hand.street,
        bet=hand.players[number].bet,
    )
    try:
        return await asyncio.to_thread(table.choose, spot, rng)
    except Exception as e:
        log.exception("The CPU at seat %s couldn't choose a move, so it checks or folds", number, exc_info=e)
        return default


def apply(hand: Hand, seat: int, action: Action) -> str:
    """Plays the move and names it for the table: a call or raise that puts in every chip is an all in"""
    try:
        hand.apply(seat, action)
    except ValueError as e:
        log.warning("Seat %s's move %r wasn't legal, so it checks or folds", seat, action, exc_info=e)
        action = fallback(hand, seat)
        hand.apply(seat, action)
    if action.move in ("call", "raise") and hand.players[seat].all_in:
        return "all_in"
    return action.move


async def give_back(table: "HoldemTable", hand: Hand) -> None:
    """An uncalled bet goes back to its owner when the betting round ends"""
    if hand.returned is None:
        return
    seat, back = hand.returned
    player = hand.players[seat]
    # The seat's tag follows its smaller bet instead of still naming the raise nobody called, and keeps saying how much
    # came back ("Got 40 back") on every table after
    table.last[seat] = {"move": "return", "amount": player.bet, "back": back}
    await table.event("act", seat=seat, move="return", amount=player.bet, stack=player.stack)


async def finish(table: "HoldemTable", hand: Hand, deck: Deck, cut: float) -> None:
    """The showdown, when two or more are still in, then the pots to their winners. A player everyone folded to
    never shows their cards"""
    ranks = {}
    if len(hand.contenders) >= 2:
        gather_bets(table, hand)
        await table.reveal(hand.contenders)
        await run_out(table, hand, deck)
        ranks = {seat: best_hand([*table.holes[seat], *table.board]) for seat in hand.contenders}
    awards, final = settle(hand, ranks, cut, hand.spots.button)
    await table.record(hand, final, awards)
    await table.announce(hand, awards, ranks)
    table.street, table.turn, table.pots, table.phase = None, None, [], "results"
    await table.push()


def gather_bets(table: "HoldemTable", hand: Hand) -> None:
    """Betting is over: the bets still in front of the seats join the pots, main pot first, so the hands turn up with
    each side pot already a pile of its own. Nobody bets again, so the round's highest bet goes too, and a run-out
    can still move on to its next street"""
    table.pots = [pot.amount for pot in hand.pots()]
    for player in hand.players.values():
        player.bet = 0
    hand.current = 0


async def run_out(table: "HoldemTable", hand: Hand, deck: Deck) -> None:
    """Once nobody can bet, the rest of the board comes out one card at a time"""
    while hand.street != "river":
        next_street(table, hand, [pot.amount for pot in hand.pots()])
        for card in [deck.draw() for count in range(STREET_CARDS[hand.street])]:
            table.board.append(card)
            await table.event("runout", card=list(card))
            await table.board_changed()
