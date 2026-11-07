"""Comings and goings at the Hold'em table: offers to buy in, topping up, standing up, the seat grace for players who
leave the window, and cashing everyone out when the table closes.

Credits leave a seat one way only: the seat lets go of them and their saved row is deleted before the bank is paid,
so nothing, a crash included, can pay a stack twice. Stacks a crash or restart left saved go back to their owners
when the cog loads (return_stacks)."""

import asyncio
import logging
import typing as t

from redbot.core.i18n import Translator

from .catalog import HOLDEM
from .games.holdem import Action
from .money import CashOut, Money
from .store import Store
from .table import Closed

if t.TYPE_CHECKING:
    from .holdem_table import Seat

_ = Translator("Vegas", __file__)

log = logging.getLogger("red.vrt.vegas.holdem")


def buy_in_range(stakes: tuple, least: int) -> tuple[int, int]:
    """The game's Min to Max, raised to what the player left with if they left in the last 30 minutes"""
    return max(stakes[2], least), max(stakes[3], least)


def lapse(future: asyncio.Future) -> None:
    """An offer nobody answered in time. None tells it apart from an answer, so its dialog still gets closed"""
    if not future.done():
        future.set_result(None)


class HoldemSeats:
    """HoldemTable's arrivals and departures"""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        # Offers to buy in: True once the player buys in, False when they say no or stand up, None when time runs out
        self.offers: dict[int, asyncio.Future] = {}
        self.offer_terms: dict[int, tuple[str, float]] = {}  # user id -> the offer's kind and when it runs out
        # Each open offer's running clock, left out while its player is asked to move: the clock waits for their turn
        self.offer_clocks: dict[int, asyncio.TimerHandle] = {}
        # A seated player who leaves the window keeps the seat for the leave grace, in case they're reconnecting
        self.seat_graces: dict[int, asyncio.Task] = {}

    def in_hand(self, seat: "Seat") -> bool:
        """True while the seat is dealt into a hand that hasn't finished"""
        return self.hand is not None and self.street is not None and seat.number in self.hand.players

    # ---------- Offers to buy in ----------

    async def offer(self, seat: "Seat", kind: str) -> None:
        """Asks a seated player to buy in: "join" when a real game is starting, "broke" when they ran out of chips.
        They have the decision time to answer, counted only while they aren't asked to move"""
        user_id = seat.member.id
        self.offers[user_id] = asyncio.get_running_loop().create_future()
        self.offer_terms[user_id] = (kind, 0.0)
        turn = self.decisions.get(user_id)
        if turn is None or turn.done():
            self.start_offer_clock(user_id)
        await self.tell(user_id, await self.offer_message(user_id))

    def start_offer_clock(self, user_id: int) -> None:
        """The offer's full decision time, from now"""
        self.hold_offer(user_id)
        loop = asyncio.get_running_loop()
        limit = self.times["decision"]
        self.offer_terms[user_id] = (self.offer_terms[user_id][0], loop.time() + limit)
        self.offer_clocks[user_id] = loop.call_later(limit, lapse, self.offers[user_id])

    def hold_offer(self, user_id: int) -> None:
        """The offer's clock stops: its player is asked to move, and their page hides the offer meanwhile"""
        clock = self.offer_clocks.pop(user_id, None)
        if clock is not None:
            clock.cancel()

    async def restart_offer(self, user_id: int) -> None:
        """The player's turn is over: an open offer gets its full time again, and their page hears the time left"""
        future = self.offers.get(user_id)
        if future is None or future.done():
            return
        # Its message is ready before the clock starts, so it says all the time is left, and an answer that lands
        # while the stakes are read leaves nothing to start over or send
        message = await self.offer_message(user_id)
        if future.done() or self.offers.get(user_id) is not future:
            return
        self.start_offer_clock(user_id)
        await self.tell(user_id, message)

    async def offer_message(self, user_id: int) -> dict:
        kind, deadline = self.offer_terms[user_id]
        scope = await self.floor.scope()
        low, high = buy_in_range(await self.stakes(), self.cog.money.left_with(scope, user_id))
        # A clock waiting on the player's turn still has all its time
        left = self.times["decision"]
        if user_id in self.offer_clocks:
            left = max(0.0, round(deadline - asyncio.get_running_loop().time(), 2))
        return {"t": "offer", "game": self.game, "kind": kind, "min": low, "max": high, "left": left}

    def no_offer(self) -> dict:
        return {"t": "offer", "game": self.game, "kind": None, "min": 0, "max": 0, "left": 0}

    async def answer_offer(self, user_id: int, yes: bool) -> None:
        future = self.offers.get(user_id)
        if future is None or future.done():
            return
        future.set_result(yes)
        await self.tell(user_id, self.no_offer())

    async def close_offer(self, user_id: int) -> None:
        """The offer is over. Its dialog closes, unless an answer closed it already"""
        future = self.offers.pop(user_id, None)
        self.offer_terms.pop(user_id, None)
        self.hold_offer(user_id)
        if future is None:
            return
        if not future.done():
            future.set_result(None)
        if future.result() is None:
            await self.tell(user_id, self.no_offer())

    async def ask_for_buy_ins(self) -> None:
        """While anyone has credits at the table, anyone without them is asked to buy in: a broke player in a real
        game, or the player practicing free when a real game is starting"""
        people = self.humans()
        if not any(seat.real > 0 for seat in people):
            return
        kind = "broke" if self.mode == "real" else "join"
        for seat in people:
            # Each offer waits on its message, so a seat earlier in the loop may have emptied since
            if self.seats[seat.number] is seat and seat.real == 0 and seat.member.id not in self.offers:
                await self.offer(seat, kind)

    def needed_offers(self) -> list[asyncio.Future]:
        """The open offers the next hand waits on: every practicer's answer when a real game is starting, and a broke
        player's only while fewer than 2 seats have credits, since the hand can't be dealt without them"""
        short = sum(seat.real > 0 for seat in self.humans()) < 2
        return [
            future
            for user_id, future in self.offers.items()
            if not future.done() and (short or self.offer_terms[user_id][0] == "join")
        ]

    async def settle_offers(self) -> None:
        """Waits until every offer the next hand needs is answered or runs out, then closes the answered ones. While
        anyone has credits at the table, whoever was asked and still has none stands up to watch. Any other offer stays
        open into the next hand, its broke player sitting out, and nobody stands up without being asked"""
        while waiting := self.needed_offers():
            await self.wait_on(asyncio.wait(waiting))
        # A buy-in still taking its credits finishes first, so its seat counts as bought in
        async with self.lock:
            asked = [user_id for user_id, future in self.offers.items() if future.done()]
            for user_id in asked:
                await self.close_offer(user_id)
            if any(seat.real > 0 for seat in self.humans()):
                for seat in self.humans():
                    if seat.member.id in asked and seat.real == 0:
                        await self.unseat(seat)

    async def take_offer(self, conn, amount: int) -> None:
        """Yes to an offer: credits from the bank onto the seat the player already holds"""
        member = conn.ctx.author
        async with self.lock:
            seat, future = self.seat_of(member.id), self.offers.get(member.id)
            if seat is None or future is None or future.done():
                return
            scope = await self.floor.scope()
            low, high = buy_in_range(await self.stakes(), self.cog.money.left_with(scope, member.id))
            problem = await self.saved_elsewhere(scope, member.id)
            if problem or (problem := await self.cog.money.buy_in(scope, member, HOLDEM, amount, low, high)):
                await self.notice(conn, problem)
                return
            # A seat without credits has no saved row, so its credits belong where they're bought now
            if seat.real == 0:
                seat.scope = scope
            seat.real += amount
            await self.cog.store.save_stack(seat.scope, self.floor.guild.id, member.id, seat.real)
        await self.answer_offer(member.id, True)
        await self.cog.send_me(self.floor, member)
        await self.push()

    async def saved_elsewhere(self, scope: int, user_id: int) -> str | None:
        """Why a player with no credits on a seat here can't buy in: they still have a saved stack, at another
        Hold'em table or waiting to be returned after a restart. A buy-in here would write over that saved row"""
        if await self.cog.store.stacked(scope, user_id) > 0:
            return _("You already have chips at another Hold'em table. Stand up there first.")
        return None

    async def decline(self, conn) -> None:
        """No to an offer: the player stands up to watch before the next hand"""
        await self.answer_offer(conn.ctx.author.id, False)

    # ---------- Topping up and standing up ----------

    async def top_up(self, conn, data: dict) -> None:
        """More credits from the bank onto the player's stack, between hands and up to the Max"""
        member = conn.ctx.author
        amount = data.get("amount")
        if self.seat_of(member.id) is None:
            return
        if not isinstance(amount, int) or isinstance(amount, bool):
            await self.notice(conn, _("Pick an amount to top up."))
            return
        async with self.lock:
            seat = self.seat_of(member.id)
            # A seat without credits buys in instead, so the Min and the re-sit rule apply to it
            if seat is None or seat.real <= 0:
                return
            if problem := await self.take_top_up(seat, amount):
                await self.notice(conn, problem)
                return
            seat.real += amount
            await self.cog.store.save_stack(seat.scope, self.floor.guild.id, member.id, seat.real)
        await self.cog.send_me(self.floor, member)
        await self.push()

    async def take_top_up(self, seat: "Seat", amount: int) -> str | None:
        """Takes the top-up out of the bank, or returns why it can't be taken"""
        if self.in_hand(seat):
            return _("You can top up between hands.")
        room = (await self.stakes())[3] - seat.real
        if room < 1:
            return _("Your stack is already at the Max.")
        return await self.cog.money.buy_in(await self.floor.scope(), seat.member, HOLDEM, amount, 1, room)

    async def stand(self, conn) -> None:
        async with self.lock:
            if (seat := self.seat_of(conn.ctx.author.id)) is not None:
                await self.get_up(seat)

    async def get_up(self, seat: "Seat") -> None:
        """Stands a player up: at once between hands or when they aren't dealt in. Otherwise they leave when the hand
        ends, and every turn they have left folds straight away. Callers hold the lock"""
        user_id = seat.member.id
        await self.answer_offer(user_id, False)
        if not self.in_hand(seat):
            await self.unseat(seat)
            return
        seat.leaving = True
        future = self.decisions.get(user_id)
        if future is not None and not future.done():
            future.set_result(Action("fold"))

    async def unseat(self, seat: "Seat", closed: bool = False) -> None:
        """Frees a player's seat and puts their credits back in their bank, then everyone sees the seat empty.
        Callers hold the lock. The seat lets go of its credits and their saved row goes before the bank is paid"""
        if self.seats[seat.number] is not seat:
            return
        self.seats[seat.number] = None
        amount, seat.real = seat.real, 0
        member = seat.member
        self.stop_seat_grace(member.id)
        await self.close_offer(member.id)
        # A player practicing free had no credits here to send home
        text = _("Texas Hold'em closed.") if closed else None
        if amount > 0:
            # Only a seat with credits owns the saved row: a stack that reaches 0 has its row deleted when the hand is
            # saved, so a seat without credits must leave alone a row kept for another table or a restart. A cancel
            # can't land between deleting the row and paying it
            text = await asyncio.shield(self.pay_out(seat.scope, member, amount, closed))
        if text:
            await self.tell(member.id, {"t": "notice", "text": text})
        await self.cog.send_me(self.floor, member)
        await self.show_empty(seat.number)

    async def pay_out(self, scope: int, member, amount: int, closed: bool) -> str | None:
        """Deletes the seat's saved row, then cashes the stack out and words the player's notice. A failed cash-out is
        logged with its amount"""
        await self.cog.store.save_stack(scope, self.floor.guild.id, member.id, 0)
        # Sitting back down within 30 minutes takes at least this much
        self.cog.money.note_left(scope, member.id, amount)
        try:
            paid = await self.cog.money.cash_out(scope, member, amount)
        except Exception as e:
            log.exception("Player %s's Hold'em stack of %s couldn't be cashed out", member.id, amount, exc_info=e)
            return None
        if closed:
            text = _("Texas Hold'em closed, so your chips went back to your bank.")
        else:
            text = _("You cashed out {paid}.").format(paid=paid.paid)
        if paid.held:
            held = _("{held} is held because your bank is full. An admin can release it.").format(held=paid.held)
            text = f"{text} {held}"
        return text

    async def show_empty(self, number: int) -> None:
        """The seat fades out, then the state without it follows. A closing table only skips the wait after the fade"""
        try:
            await self.event("unseat", seat=number)
        except Closed as e:
            log.debug("Seat %s emptied while the table closes: %r", number, e)
        await self.push()

    async def unseat_all(self, closed: bool = False) -> None:
        """Everyone stands up and is cashed out. Callers hold the lock"""
        for seat in self.humans():
            try:
                await self.unseat(seat, closed)
            except Exception as e:
                log.exception("Couldn't stand player %s up", seat.member.id, exc_info=e)

    async def holdem_open(self) -> bool:
        scope = await self.floor.scope()
        casino = await self.cog.store.casino(scope)
        game = await self.cog.store.game(scope, HOLDEM)
        return casino.is_open and game.is_open

    # ---------- Leaving the window ----------

    async def enter(self, conn) -> None:
        user_id = conn.ctx.author.id
        self.stop_seat_grace(user_id)
        await super().enter(conn)
        # A page that reloads mid-offer gets its dialog back
        future = self.offers.get(user_id)
        if future is not None and not future.done():
            await conn.send(await self.offer_message(user_id))

    async def leave(self, conn) -> None:
        await super().leave(conn)
        user_id = conn.ctx.author.id
        # A closed table holds no seats: connections dropped by an unload would otherwise start timers nothing stops
        if self.closing.is_set() or self.is_here(user_id) or self.seat_of(user_id) is None:
            return
        # The seat grace takes over from the shared turn grace: the player's turn keeps its clock meanwhile, and they
        # fold only if the grace runs out
        self.stop_grace(user_id)
        self.stop_seat_grace(user_id)
        self.seat_graces[user_id] = asyncio.create_task(self.free_seat_later(user_id))

    def can_answer(self, user_id: int) -> bool:
        # A seated player in their leave grace keeps their turn: they may be reconnecting
        return super().can_answer(user_id) or user_id in self.seat_graces

    def stop_seat_grace(self, user_id: int) -> None:
        task = self.seat_graces.pop(user_id, None)
        if task is not None:
            task.cancel()

    async def free_seat_later(self, user_id: int) -> None:
        await asyncio.sleep(self.times["grace"])
        # Out of seat_graces before the seat goes, so nothing can cancel this task in the middle of a cash-out
        self.seat_graces.pop(user_id, None)
        try:
            async with self.lock:
                seat = self.seat_of(user_id)
                if seat is not None and not self.is_here(user_id):
                    await self.get_up(seat)
        except Exception as e:
            log.exception("Couldn't free player %s's seat after they left", user_id, exc_info=e)
        # The held seat kept the window's floor open; with nobody back, it can go now
        if self.floor.idle():
            self.cog.floor_done(self.floor)

    # ---------- Closing ----------

    async def refund(self) -> None:
        """A session that can't go on: a hand cut short goes back to where it started, with no cut, and everyone is
        cashed out"""
        async with self.lock:
            for number, amount in self.start.items():
                if (seat := self.seats[number]) is not None:
                    seat.real = amount
            self.start = {}
            await self.unseat_all()

    async def close(self) -> None:
        """Stops the session at its next wait, which cashes everyone out, then cashes out anyone it didn't"""
        for user_id in list(self.seat_graces):
            self.stop_seat_grace(user_id)
        await super().close()
        async with self.lock:
            await self.unseat_all()

    def busy(self) -> bool:
        # Seated players and held seats keep the window's floor, so a reconnect finds the same table and stacks
        return super().busy() or bool(self.humans()) or bool(self.seat_graces)


async def owner_of(bot, row, global_bank: bool):
    """The person a saved stack belongs to, or None when the bot can't find them. The bot's cache comes first, then
    Discord itself: without the members intent the cache misses most members"""
    try:
        if global_bank:
            return bot.get_user(row.user_id) or await bot.fetch_user(row.user_id)
        guild = bot.get_guild(row.guild_id)
        if guild is None:
            return None
        return guild.get_member(row.user_id) or await guild.fetch_member(row.user_id)
    except Exception as e:
        log.debug("Couldn't fetch player %s from Discord: %r", row.user_id, e)
        return None


async def return_stacks(bot, store: Store, money: Money) -> int:
    """Pays the stacks a crash or restart left saved back to their owners' banks. A stack whose owner can't be found
    stays saved, to be tried again on the next load. Returns how many were paid"""
    global_bank = await money.bank.is_global()
    paid = 0
    for row in await store.stacks():
        owner = await owner_of(bot, row, global_bank)
        if owner is None:
            log.warning(
                "Player %s wasn't found, so their saved Hold'em stack of %s stays saved", row.user_id, row.amount
            )
            continue
        # A cancel, like an unload during startup, can't land between deleting the row and paying it
        cashed = await asyncio.shield(pay_back(store, money, row, owner))
        if cashed is None:
            continue
        log.info(
            "Returned player %s's saved Hold'em stack of %s: %s to their bank, %s held",
            row.user_id,
            row.amount,
            cashed.paid,
            cashed.held,
        )
        paid += 1
    return paid


async def pay_back(store: Store, money: Money, row, owner) -> CashOut | None:
    """Deletes a saved stack, then pays it to its owner. Deleted first, so a crash in between can never pay it twice.
    None when the payment failed, which is logged"""
    await store.save_stack(row.scope, row.guild_id, row.user_id, 0)
    try:
        return await money.cash_out(row.scope, owner, row.amount)
    except Exception as e:
        log.exception("Player %s's saved Hold'em stack of %s couldn't be paid", row.user_id, row.amount, exc_info=e)
        return None
