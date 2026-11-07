"""Texas Hold'em's table: the seats and their stacks, the session of hands, and who may see which cards.
How one hand plays lives in holdem_dealer.

Alone at the table, a player practices free against CPUs with play chips. With 2 or more people bought in, hands are
played for their credits. Credits at the table are saved as each hand starts and ends, so a crash can't lose them."""

import asyncio
import logging
import random
import typing as t
from dataclasses import dataclass

from redbot.core.i18n import Translator

from .catalog import HOLDEM
from .games import holdem_cpu
from .games.cards import Card, Deck
from .games.holdem import SEAT_COUNT, Action, Award, Hand, blinds
from .games.holdem_cpu import Spot
from .games.poker import HandRank, describe
from .holdem_dealer import play_hand
from .holdem_seats import HoldemSeats, buy_in_range
from .table import Closed, Table

_ = Translator("Vegas", __file__)

log = logging.getLogger("red.vrt.vegas.holdem")

CPU_COUNT = 3
PRACTICE_BLINDS = 100  # practice stacks, in big blinds
HAND_GAP = 3.0  # seconds from the end of one hand to the next deal
BIG_POT_BLINDS = 50  # a pot this many big blinds or bigger gets the big celebration
CPU_NAMES = ("Rosa", "Dex", "Mabel", "Otto", "Juno", "Hank")
# What the page sends the Hold'em table itself
MESSAGES = ("sit", "buy_in", "top_up", "stand", "decline", "move")


@dataclass
class Seat:
    number: int
    member: t.Any | None  # None for a CPU
    name: str
    real: int = 0  # credits at the table (saved in holdem_stack)
    # Where the credits were bought in: their saved row's scope, kept if the casino's mode switches meanwhile
    scope: int | None = None
    play: int = 0  # practice chips
    waiting: bool = False  # joined a running real game, waiting for the big blind
    post: bool = False  # chose to pay a big blind to play the next hand
    timeouts: int = 0
    leaving: bool = False  # stands up when the hand ends

    @property
    def cpu(self) -> bool:
        return self.member is None

    @property
    def id(self) -> int:
        return -(self.number + 1) if self.member is None else self.member.id


def valid_seat(number: t.Any) -> bool:
    return isinstance(number, int) and not isinstance(number, bool) and 0 <= number < SEAT_COUNT


class HoldemTable(HoldemSeats, Table):
    """Six seats and a session of hands, dealt one after another while anyone is seated. Arrivals and departures
    live in HoldemSeats"""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        self.seats: list[Seat | None] = [None] * SEAT_COUNT
        self.mode = "idle"  # "idle" | "practice" | "real"
        self.button: int | None = None
        self.hand_no = 0
        self.hand: Hand | None = None
        self.street: str | None = None  # None between hands
        self.turn: int | None = None
        self.board: list[Card] = []
        self.holes: dict[int, list[Card]] = {}  # seat number -> 2 cards
        self.shown: dict[int, dict] = {}  # hands turned face up at showdown
        self.last: dict[int, dict] = {}  # each seat's last move this betting round
        self.pots: list[int] = []  # swept pots; this round's bets are still in front of the seats
        self.start: dict[int, int] = {}  # seat number -> real stack when the running hand started
        self.limits: tuple[int, int, int, int, float] | None = None  # small, big, min, max, cut
        self.choose: t.Callable[[Spot, random.Random], Action] = holdem_cpu.choose

    def new_deck(self) -> Deck:
        """A freshly shuffled deck for each hand"""
        deck = Deck(self.cog.rng)
        deck.fresh()
        return deck

    # ---------- Seats ----------

    def seat_of(self, user_id: int) -> Seat | None:
        return next((seat for seat in self.seats if seat is not None and seat.id == user_id), None)

    def humans(self) -> list[Seat]:
        return [seat for seat in self.seats if seat is not None and not seat.cpu]

    def chips(self, seat: Seat) -> int:
        """The seat's stack in the current mode: credits in a real game, play chips in practice, and between sessions
        the credits of anyone who bought in"""
        if self.mode == "idle" and seat.real > 0:
            return seat.real
        return seat.real if self.mode == "real" else seat.play

    async def stakes(self) -> tuple[int, int, int, int, float]:
        """Small blind, big blind, min and max buy-in and the cut percent, as the admins have them set now"""
        scope = await self.floor.scope()
        game = await self.cog.store.game(scope, HOLDEM)
        small, big = blinds(game.max_bet)
        return small, big, game.min_bet, game.max_bet, game.cut or 0.0

    async def handle(self, conn, kind: str, data: dict) -> None:
        if kind == "sit":
            await self.sit(conn, data.get("seat"))
        elif kind == "buy_in":
            await self.buy_in(conn, data)
        elif kind == "top_up":
            await self.top_up(conn, data)
        elif kind == "stand":
            await self.stand(conn)
        elif kind == "decline":
            await self.decline(conn)
        elif kind == "move":
            await self.move(conn, data)

    def seat_problem(self, number: int, free: bool) -> str | None:
        """Why this seat can't be taken now. A free seat is only for the first person at the table"""
        if self.closing.is_set():
            return _("This table is closing.")
        if free and self.humans():
            return _("Buy in to sit.")
        if self.seats[number] is not None:
            return _("That seat was just taken.")
        return None

    async def sit(self, conn, number: t.Any) -> None:
        """A free practice seat for the first person at the table. Everyone after them buys in"""
        member = conn.ctx.author
        if not valid_seat(number) or self.seat_of(member.id) is not None:
            return
        if problem := await self.cog.money.access_problem(await self.floor.scope(), member, HOLDEM):
            await self.notice(conn, problem)
            return
        big = (await self.stakes())[1]
        async with self.lock:
            # A second device of the same person may have sat while the stakes were read
            if self.seat_of(member.id) is not None:
                return
            if problem := self.seat_problem(number, free=True):
                await self.notice(conn, problem)
                return
            self.seats[number] = Seat(number, member, member.display_name, play=PRACTICE_BLINDS * big)
            self.start_session()
        await self.seated(number)

    async def buy_in(self, conn, data: dict) -> None:
        """Credits from the bank onto an empty seat, between the Min and Max (or more, after leaving recently). A seat
        of None answers an offer for the seat the player already holds"""
        member = conn.ctx.author
        number, amount = data.get("seat"), data.get("amount")
        if number is not None and (not valid_seat(number) or self.seat_of(member.id) is not None):
            return
        if not isinstance(amount, int) or isinstance(amount, bool):
            await self.notice(conn, _("Pick an amount to buy in."))
            return
        if number is None:
            await self.take_offer(conn, amount)
            return
        async with self.lock:
            if self.seat_of(member.id) is not None:
                return
            if problem := self.seat_problem(number, free=False):
                await self.notice(conn, problem)
                return
            scope = await self.floor.scope()
            stakes = await self.stakes()
            low, high = buy_in_range(stakes, self.cog.money.left_with(scope, member.id))
            problem = await self.saved_elsewhere(scope, member.id)
            if problem or (problem := await self.cog.money.buy_in(scope, member, HOLDEM, amount, low, high)):
                await self.notice(conn, problem)
                return
            seat = Seat(number, member, member.display_name, real=amount, scope=scope, play=PRACTICE_BLINDS * stakes[1])
            if self.mode == "real":
                # Card-room rules: pay a big blind to play the next hand, or wait for the big blind to reach the seat
                seat.post = bool(data.get("post"))
                seat.waiting = not seat.post
            self.seats[number] = seat
            await self.cog.store.save_stack(scope, self.floor.guild.id, member.id, amount)
            self.start_session()
        await self.cog.send_me(self.floor, member)
        await self.seated(number)
        # Anyone practicing free is asked to buy in too, so a real game can start
        await self.ask_for_buy_ins()

    async def seated(self, number: int) -> None:
        """Everyone sees the new seat, then it fades in"""
        await self.push()
        await self.event("seat", seat=number)

    def start_session(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self.run())

    # ---------- The session ----------

    async def run(self) -> None:
        """Hand after hand, a few seconds apart, until nobody is seated"""
        try:
            while await self.prepare():
                await play_hand(self)
                await self.pause(HAND_GAP)
                await self.after_hand()
        except Closed as e:
            log.debug("The Hold'em table closed mid-session: %r", e)
            await self.refund()
        except asyncio.CancelledError as e:
            log.debug("The Hold'em session was cancelled: %r", e)
            await self.refund()
            raise
        except Exception as e:
            log.error("A Hold'em session failed", exc_info=e)
            await self.refund()
        finally:
            self.clear_hand()
            self.reset()
        await self.push()
        if self.floor.idle():
            self.cog.floor_done(self.floor)

    async def prepare(self) -> bool:
        """Settles who plays the next hand, picks its mode, and seats or sends away the CPUs. True when a hand can be
        dealt"""
        self.limits = await self.stakes()
        if await self.holdem_open():
            await self.ask_for_buy_ins()
            await self.settle_offers()
        # Read again after the offers, which may wait a while: if admins closed Hold'em or the casino, the last hand
        # has finished, so everyone is cashed out
        if not await self.holdem_open():
            async with self.lock:
                await self.unseat_all(closed=True)
        if not self.humans():
            await self.clear_cpus()
            # Someone may have sat down while the CPUs left; no wait comes between this check and the session's end
            if not self.humans():
                self.mode = "idle"
                return False
        if sum(seat.real > 0 for seat in self.humans()) >= 2:
            await self.play_real()
        else:
            await self.play_practice()
        active, waiting = self.lineup()
        return len(active) + len(waiting) >= 2

    async def play_real(self) -> None:
        if self.mode != "real":
            # Everyone in the first real hand after practice is dealt in with normal blinds
            for seat in self.humans():
                seat.waiting = seat.post = False
        self.mode = "real"
        await self.clear_cpus()

    async def play_practice(self) -> None:
        self.mode = "practice"
        await self.seat_cpus()
        big = self.limits[1]
        for seat in self.seats:
            if seat is not None and seat.play < big:
                seat.play = PRACTICE_BLINDS * big

    async def seat_cpus(self) -> None:
        """CPUs take the lowest empty seats, up to CPU_COUNT of them"""
        big = self.limits[1]
        async with self.lock:
            missing = CPU_COUNT - sum(seat is not None and seat.cpu for seat in self.seats)
            empty = [number for number, seat in enumerate(self.seats) if seat is None][: max(0, missing)]
            for number in empty:
                self.seats[number] = Seat(number, None, self.cpu_name(), play=PRACTICE_BLINDS * big)
        for number in empty:
            await self.seated(number)

    def cpu_name(self) -> str:
        used = {seat.name for seat in self.seats if seat is not None}
        names = [_("CPU {name}").format(name=name) for name in CPU_NAMES]
        return self.cog.rng.choice([name for name in names if name not in used])

    async def clear_cpus(self) -> None:
        """The CPUs leave: the table without them goes out first, so a real game's stacks show at once, and the page
        fades the CPUs out as they go"""
        gone = [seat.number for seat in self.seats if seat is not None and seat.cpu]
        for number in gone:
            self.seats[number] = None
        if gone:
            await self.push()
        for number in gone:
            await self.event("unseat", seat=number)

    def lineup(self) -> tuple[list[int], list[int]]:
        """Seats with chips: those dealt in as usual, and those waiting for the big blind to reach them"""
        active, waiting = [], []
        for seat in self.seats:
            if seat is None or self.chips(seat) <= 0:
                continue
            (waiting if self.mode == "real" and seat.waiting else active).append(seat.number)
        return active, waiting

    async def after_hand(self) -> None:
        """Players who stood up mid-hand leave, then the finished hand leaves the table just before the next deal"""
        async with self.lock:
            for seat in self.humans():
                if seat.leaving:
                    await self.unseat(seat)
        self.clear_hand()

    def clear_hand(self) -> None:
        self.hand, self.street, self.turn = None, None, None
        self.board, self.holes, self.shown, self.last, self.pots, self.start = [], {}, {}, {}, [], {}
        self.phase = "idle"

    # ---------- Results ----------

    async def record(self, hand: Hand, final: dict[int, int], awards: list[Award]) -> None:
        """A finished hand's stacks go to the seats: play chips in practice, credits in a real game. Real stacks are
        saved and the hand counts in each player's stats. The cut isn't paid to anyone"""
        real = self.mode == "real"
        for number, chips in final.items():
            seat = self.seats[number]
            if seat is None or (real and seat.cpu):
                continue
            if real:
                seat.real = chips
            else:
                seat.play = chips
        if real:
            await self.save_real(hand, awards)
        # The hand is settled, so nothing can take these stacks back to where the hand started
        self.start = {}

    async def save_real(self, hand: Hand, awards: list[Award]) -> None:
        """Every dealt player's stack is saved in one write, then the hand counts in their stats. Each seat's row and
        stats stay where its credits were bought in"""
        winners = {number for award in awards for number in award.winners}
        people = [self.seats[n] for n in hand.spots.dealt if self.seats[n] is not None and not self.seats[n].cpu]
        guild_id = self.floor.guild.id
        await self.cog.store.save_stacks([(seat.scope, guild_id, seat.member.id, seat.real) for seat in people])
        # Saved, so the hand is settled: a stats failure can no longer take these stacks back to the hand's start
        self.start = {}
        for seat in people:
            await self.cog.money.count_hand(seat.scope, seat.member.id, HOLDEM, seat.number in winners)

    async def announce(self, hand: Hand, awards: list[Award], ranks: dict[int, HandRank]) -> None:
        """Who won what. The best five cards show only for winners whose hands were shown"""
        views = [
            {"amount": sum(a.shares.values()), "winners": list(a.winners), "shares": dict(a.shares)} for a in awards
        ]
        best = {n: [list(card) for card in ranks[n].cards] for a in awards for n in a.winners if n in ranks}
        awarded = sum(view["amount"] for view in views)
        cut = sum(award.cut for award in awards)
        await self.event("win", awards=views, best=best, cut=cut, big=awarded >= BIG_POT_BLINDS * hand.big)

    # ---------- Moves ----------

    async def decide(self, user_ids: list[int], allowed: tuple | dict, default: t.Any, limit: float) -> dict:
        """A player's turn. An open offer to buy in waits while they're asked to move, and starts over with its full
        time once they have, so the action bar never hides an offer whose clock is running"""
        for user_id in user_ids:
            self.hold_offer(user_id)
        moves = await super().decide(user_ids, allowed, default, limit)
        for user_id in user_ids:
            await self.restart_offer(user_id)
        return moves

    async def bet(self, conn, data: dict) -> None:
        """Credits only reach a Hold'em table through a buy-in, never the other tables' betting"""

    async def press_go(self, conn) -> None:
        """Hands deal by themselves; there is no betting window to skip"""

    async def move(self, conn, data: dict) -> None:
        """The asked player's move. Anything not legal right now is ignored, and their clock keeps running"""
        user_id = conn.ctx.author.id
        future = self.decisions.get(user_id)
        if future is None or future.done():
            return
        if (action := self.read_move(user_id, data)) is not None:
            future.set_result(action)

    def read_move(self, user_id: int, data: dict) -> Action | None:
        seat = self.seat_of(user_id)
        move = data.get("move")
        if seat is None or self.hand is None or self.hand.to_act != seat.number:
            return None
        if not isinstance(move, str) or move not in self.allowed.get(user_id, ()):
            return None
        if move != "raise":
            return Action(move)
        legal = self.hand.legal(seat.number)
        amount = data.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or not legal.min_to <= amount <= legal.max_to:
            return None
        return Action("raise", amount)

    # ---------- What each person sees ----------

    def extra_state(self) -> dict:
        stakes = None
        if self.limits is not None:
            stakes = dict(zip(("small", "big", "min", "max", "cut"), self.limits, strict=True))
        return {
            "mode": self.mode,
            "stakes": stakes,
            "seats": [self.seat_view(seat) for seat in self.seats],
            "button": self.button,
            "board": [list(card) for card in self.board],
            "pots": list(self.pots),
            "turn": self.turn,
            "street": self.street,
            "hand": self.hand_no,
            "shown": self.shown,
            "waiting": [str(user_id) for user_id in self.decisions],
        }

    def seat_view(self, seat: Seat | None) -> dict | None:
        """A seat as everyone may see it: how many cards it holds, never which"""
        if seat is None:
            return None
        player = None
        if self.hand is not None and self.street is not None:
            player = self.hand.players.get(seat.number)
        return {
            "seat": seat.number,
            "id": str(seat.id),
            "name": seat.name,
            "avatar": None if seat.cpu else seat.member.display_avatar.url,
            "cpu": seat.cpu,
            "stack": self.chips(seat) if player is None else player.stack,
            "bet": 0 if player is None else player.bet,
            "in_hand": player is not None,
            "folded": player is not None and player.folded,
            "all_in": player is not None and player.all_in and not player.folded,
            "cards": 2 if player is not None and not player.folded else 0,
            "last": self.last.get(seat.number),
            "waiting": seat.waiting,
            "away": not seat.cpu and not self.is_here(seat.member.id),
        }

    def hole_message(self, user_id: int) -> dict | None:
        """The player's own two cards and their hand's name, while they are still in the hand"""
        seat = self.seat_of(user_id)
        if seat is None or self.hand is None or self.street is None or seat.number not in self.holes:
            return None
        if self.hand.players[seat.number].folded:
            return None
        hole = self.holes[seat.number]
        return {
            "t": "hole",
            "game": self.game,
            "hand": self.hand_no,
            "cards": [list(card) for card in hole],
            "name": describe([*hole, *self.board]),
        }

    async def send_holes(self) -> None:
        """Each person still in the hand hears their own cards, on every device they have open"""
        for seat in self.humans():
            if (message := self.hole_message(seat.member.id)) is not None:
                await self.tell(seat.member.id, message)

    def shown_hands(self, numbers: t.Iterable[int]) -> dict[int, dict]:
        hands = {}
        for number in numbers:
            hole = self.holes[number]
            hands[number] = {"cards": [list(card) for card in hole], "name": describe([*hole, *self.board])}
        return hands

    async def reveal(self, numbers: list[int]) -> None:
        """Showdown: the hands still in turn face up for everyone, and the bets left join the pots, each side pot its
        own pile"""
        self.shown = self.shown_hands(numbers)
        await self.event("show", hands=self.shown, pots=list(self.pots))

    async def board_changed(self) -> None:
        """A new shared card: hand names change for the players still in and for the hands already shown"""
        await self.send_holes()
        if self.shown:
            self.shown = self.shown_hands(list(self.shown))
        await self.push()

    def ask_message(self, user_id: int) -> dict:
        seat = self.seat_of(user_id)
        legal = self.hand.legal(seat.number)
        return {
            "t": "ask",
            "game": self.game,
            "moves": list(self.allowed[user_id]),
            "call": legal.call,
            "min_to": legal.min_to,
            "max_to": legal.max_to,
            "pot": self.hand.pot_total,
            "bet": self.hand.players[seat.number].bet,
        }

    async def enter(self, conn) -> None:
        """Someone arriving or reconnecting sees the table, then gets their buttons and their own cards back"""
        if self.task is None:
            # A running session reads the stakes before each hand
            self.limits = await self.stakes()
        await super().enter(conn)
        if (message := self.hole_message(conn.ctx.author.id)) is not None:
            await conn.send(message)
