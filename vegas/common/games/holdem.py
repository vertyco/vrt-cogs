"""No-limit Texas Hold'em betting rules: seats and blinds, legal moves, side pots, the casino's cut and who wins what.
Pure rules with no money: every amount is in table chips"""

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from .poker import HandRank

SEAT_COUNT = 6
BUY_IN_BLINDS = 100  # the Max buy-in is this many big blinds
CUT_CAP_BLINDS = 3  # the casino never cuts more than this many big blinds from one hand
STREETS = ("preflop", "flop", "turn", "river")


def blinds(max_buy_in: int) -> tuple[int, int]:
    """The small and big blind for a Max buy-in: the big is Max / 100, the small half that, never below 1"""
    big = max(1, max_buy_in // BUY_IN_BLINDS)
    return max(1, big // 2), big


def clockwise(start: int, seats: Iterable[int]) -> list[int]:
    """Seats in clockwise order (rising numbers, wrapping at 6), beginning with the first seat after `start`"""
    return sorted(set(seats), key=lambda seat: (seat - start - 1) % SEAT_COUNT)


@dataclass(frozen=True)
class Positions:
    button: int
    small: int
    big: int
    dealt: tuple[int, ...]  # every seat in the hand, clockwise, starting with the seat after the button
    joined: frozenset[int]  # waiting seats that join this hand


def positions(active: Iterable[int], waiting: Iterable[int], last_button: int | None) -> Positions | None:
    """Who has the button and the blinds this hand. A waiting seat joins when the big blind reaches it, or at once
    when fewer than 2 seats are active. None when fewer than 2 seats would be dealt"""
    active = set(active)
    waiting = set(waiting) - active
    joined = set()
    if len(active) < 2:
        joined = set(waiting)
        active |= waiting
        waiting = set()
    if len(active) < 2:
        return None
    button = min(active) if last_button is None else clockwise(last_button, active)[0]
    small = clockwise(button, active)[0]
    big = clockwise(small, active | waiting)[0]
    if big in waiting:
        joined.add(big)
    dealt = tuple(clockwise(button, active | joined))
    if len(dealt) == 2:
        # Heads-up the button posts the small blind and the other seat the big
        small, big = button, small
    return Positions(button, small, big, dealt, frozenset(joined))


@dataclass
class Action:
    move: str  # "fold" | "check" | "call" | "raise" (a first bet is a raise from 0)
    amount: int = 0  # raise only: the player's whole bet this round after raising


@dataclass(frozen=True)
class Legal:
    fold: bool  # only when there is something to call
    check: bool
    call: int  # chips a call adds (capped at the stack); 0 when check is free
    min_to: int | None  # None when the player may not raise
    max_to: int | None

    def moves(self) -> tuple[str, ...]:
        options = (
            ("fold", self.fold),
            ("check", self.check),
            ("call", self.call > 0),
            ("raise", self.min_to is not None),
        )
        return tuple(name for name, allowed in options if allowed)


NO_MOVES = Legal(False, False, 0, None, None)


@dataclass
class Player:
    seat: int
    stack: int  # chips behind
    bet: int = 0  # chips in this betting round
    total: int = 0  # chips in this hand, bet included
    folded: bool = False
    acted: bool = False  # acted since the last full bet or raise

    @property
    def all_in(self) -> bool:
        return self.stack == 0


@dataclass(frozen=True)
class Pot:
    amount: int
    eligible: tuple[int, ...]


class Hand:
    """One hand's betting, from the blinds to the end of the river"""

    def __init__(self, stacks: dict[int, int], spots: Positions, small: int, big: int, posts: Iterable[int] = ()):
        self.spots = spots
        self.small = small
        self.big = big
        self.players = {seat: Player(seat, stacks[seat]) for seat in spots.dealt}
        self.street = "preflop"
        self.current = 0  # the highest bet this round
        self.min_raise = big  # the smallest raise allowed: the last full bet or raise this round
        self.saw_flop = False
        self.returned: tuple[int, int] | None = None  # (seat, chips) given back when this betting round ended
        self.posted: list[tuple[int, str, int]] = []
        self.post(spots.small, "small", small)
        self.post(spots.big, "big", big)
        extra = set(posts) - {spots.small, spots.big}
        for seat in spots.dealt:
            if seat in extra:
                self.post(seat, "post", big)
        # Index into spots.dealt where the search for the next player to act starts
        self.cursor = (spots.dealt.index(spots.big) + 1) % len(spots.dealt)
        if self.round_over:
            # Blinds alone can end the first round, when nobody left can match the big blind
            self.return_uncalled()

    def put(self, player: Player, chips: int) -> int:
        """Moves chips from a stack into its bet, never more than the stack holds"""
        chips = min(chips, player.stack)
        player.stack -= chips
        player.bet += chips
        player.total += chips
        self.current = max(self.current, player.bet)
        return chips

    def post(self, seat: int, kind: str, amount: int) -> None:
        """A forced bet: blinds and posts don't count as acting, and a short stack posts what it has"""
        chips = self.put(self.players[seat], amount)
        self.posted.append((seat, kind, chips))

    def live(self) -> list[Player]:
        """Players who can still put chips in: not folded and not all in"""
        return [player for player in self.players.values() if not player.folded and not player.all_in]

    def waits_on(self, player: Player) -> bool:
        """True when this player still has a choice to make this round. A player with nothing to call and nobody
        left who could answer a raise has none, so the hand moves on without asking them to check"""
        if player.folded or player.all_in:
            return False
        if player.bet < self.current:
            return True
        return not player.acted and any(other is not player for other in self.live())

    @property
    def to_act(self) -> int | None:
        order = self.spots.dealt
        for step in range(len(order)):
            seat = order[(self.cursor + step) % len(order)]
            if self.waits_on(self.players[seat]):
                return seat
        return None

    @property
    def round_over(self) -> bool:
        return self.to_act is None

    def legal(self, seat: int) -> Legal:
        player = self.players[seat]
        if player.folded or player.all_in:
            return NO_MOVES
        owed = self.current - player.bet
        call = min(owed, player.stack)
        # A player who already acted and now faces a short all-in may only call or fold, and nobody raises when
        # every other player still in is all in
        can_raise = not player.acted and player.stack > owed and any(other is not player for other in self.live())
        if not can_raise:
            return Legal(owed > 0, owed == 0, call, None, None)
        most = player.bet + player.stack
        return Legal(owed > 0, owed == 0, call, min(self.current + self.min_raise, most), most)

    def apply(self, seat: int, action: Action) -> Action:
        """Plays a move for the seat to act. ValueError when it isn't their turn or the move isn't legal"""
        if seat is None or seat != self.to_act:
            raise ValueError(f"It is not seat {seat}'s turn")
        legal = self.legal(seat)
        if action.move not in legal.moves():
            raise ValueError(f"{action.move!r} is not a legal move for seat {seat}")
        player = self.players[seat]
        if action.move == "raise":
            self.raise_to(player, action.amount, legal)
        elif action.move == "call":
            self.put(player, legal.call)
        elif action.move == "fold":
            player.folded = True
        player.acted = True
        self.cursor = (self.spots.dealt.index(seat) + 1) % len(self.spots.dealt)
        applied = Action(action.move, player.bet if action.move == "raise" else 0)
        if self.round_over:
            self.return_uncalled()
        return applied

    def return_uncalled(self) -> None:
        """When a betting round ends, gives the highest bet back down to the next-highest bet anyone made this round
        (folded players included). Nobody matched those chips, so they never reach a pot or the casino's cut"""
        top = max(self.players.values(), key=lambda player: player.bet)
        matched = max(player.bet for player in self.players.values() if player is not top)
        extra = top.bet - matched
        if extra > 0:
            top.stack += extra
            top.bet -= extra
            top.total -= extra
            self.current = matched
            self.returned = (top.seat, extra)

    def raise_to(self, player: Player, amount: int, legal: Legal) -> None:
        if type(amount) is not int or not legal.min_to <= amount <= legal.max_to:
            raise ValueError(f"A raise to {amount!r} is outside {legal.min_to} to {legal.max_to}")
        size = amount - self.current
        if size >= self.min_raise:
            # A full raise: everyone else gets to act again
            self.min_raise = size
            for other in self.players.values():
                other.acted = False
        self.put(player, amount - player.bet)

    def next_street(self) -> str:
        """Ends the betting round and moves to the next street. Only while 2 or more players are still in, so a hand
        everyone folded never sees a flop (and is never cut)"""
        if not self.round_over:
            raise ValueError("The betting round is not over")
        if len(self.contenders) < 2:
            raise ValueError("The hand is over: everyone else folded")
        if self.street == STREETS[-1]:
            raise ValueError("The river is the last street")
        self.street = STREETS[STREETS.index(self.street) + 1]
        self.saw_flop = True
        self.returned = None
        for player in self.players.values():
            player.bet = 0
            player.acted = False
        self.current = 0
        self.min_raise = self.big
        self.cursor = 0
        return self.street

    @property
    def contenders(self) -> list[int]:
        """Seats still in the hand (not folded), in dealing order"""
        return [seat for seat in self.spots.dealt if not self.players[seat].folded]

    @property
    def betting_done(self) -> bool:
        """The round is over and one or no player can still bet: the board runs out without betting.
        False once everyone else folded, since there is nothing to run out"""
        return len(self.contenders) >= 2 and self.round_over and len(self.live()) <= 1

    @property
    def pot_total(self) -> int:
        return sum(player.total for player in self.players.values())

    def slices(self) -> list[tuple[int, tuple[int, ...]]]:
        """The chips in the hand cut at every player's total: (amount, who can win it)"""
        result = []
        floor = 0
        for level in sorted({player.total for player in self.players.values() if player.total > 0}):
            payers = {seat for seat, player in self.players.items() if player.total > floor}
            amount = sum(min(self.players[seat].total, level) - floor for seat in payers)
            eligible = tuple(seat for seat in self.spots.dealt if seat in payers and not self.players[seat].folded)
            result.append((amount, eligible))
            floor = level
        return result

    def pots(self) -> list[Pot]:
        """The main pot first, then side pots, for a finished betting round (uncalled chips are already back).
        Neighbouring slices the same seats can win make one pot; folded chips above the last level join the last pot"""
        merged: list[tuple[int, tuple[int, ...]]] = []
        for amount, eligible in self.slices():
            if merged and (not eligible or eligible == merged[-1][1]):
                merged[-1] = (merged[-1][0] + amount, merged[-1][1])
            else:
                merged.append((amount, eligible))
        return [Pot(amount, eligible) for amount, eligible in merged]

    def stacks(self) -> dict[int, int]:
        """Every dealt seat's chips behind"""
        return {seat: player.stack for seat, player in self.players.items()}


@dataclass(frozen=True)
class Award:
    pot: Pot
    cut: int
    winners: tuple[int, ...]
    shares: dict[int, int]


def house_cut(hand: Hand, raked: int, cut_percent: float) -> int:
    """The casino's cut of the whole hand: a percent of the pots, at most 3 big blinds, nothing before the flop"""
    if not hand.saw_flop or not cut_percent:
        return 0
    # Fraction keeps a percent like 2.28 exact, where float math can floor 57 down to 56
    return min(math.floor(Fraction(str(cut_percent)) * raked / 100), CUT_CAP_BLINDS * hand.big)


def pot_cuts(pots: list[Pot], raked: int, total: int) -> list[int]:
    """Each pot's part of the cut, by its size. The leftover comes from the first pot (spilling to the next only if
    a tiny first pot can't hold it)"""
    if not total:
        return [0] * len(pots)
    cuts = [total * pot.amount // raked for pot in pots]
    leftover = total - sum(cuts)
    for index, pot in enumerate(pots):
        extra = min(leftover, pot.amount - cuts[index])
        cuts[index] += extra
        leftover -= extra
    return cuts


def pot_winners(pot: Pot, ranks: dict[int, HandRank], button: int) -> tuple[int, ...]:
    """The eligible seats with the best hand, clockwise from the button. A lone contender needs no hand"""
    if len(pot.eligible) == 1:
        return pot.eligible
    best = max(ranks[seat] for seat in pot.eligible)
    return tuple(clockwise(button, [seat for seat in pot.eligible if ranks[seat] == best]))


def split(chips: int, winners: tuple[int, ...]) -> dict[int, int]:
    """Even shares, with the odd chips to the first winner"""
    each, odd = divmod(chips, len(winners))
    shares = {seat: each for seat in winners}
    shares[winners[0]] += odd
    return shares


def settle(
    hand: Hand, ranks: dict[int, HandRank], cut_percent: float, button: int
) -> tuple[list[Award], dict[int, int]]:
    """Awards every pot, and every dealt seat's final stack (chips behind, returned bets included, + winnings)"""
    pots = hand.pots()
    raked = sum(pot.amount for pot in pots)
    cuts = pot_cuts(pots, raked, house_cut(hand, raked, cut_percent))
    final = hand.stacks()
    awards = []
    for pot, cut in zip(pots, cuts, strict=True):
        winners = pot_winners(pot, ranks, button)
        shares = split(pot.amount - cut, winners)
        for seat, chips in shares.items():
            final[seat] += chips
        awards.append(Award(pot, cut, winners, shares))
    return awards, final
