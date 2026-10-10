"""Shared tables. A Floor is everyone in one Activity window; it holds one Table per game.

A round goes: betting, playing, results. Alone at a table, a bet starts the round at once. With others there, the
first bet opens a betting window that anyone who has bet can skip. Each game's Table subclass plays its round in
play(); everything about money goes through Money, so each player is checked and paid as if they played alone.
"""

import asyncio
import logging
import typing as t
from dataclasses import dataclass

from redbot.core.i18n import Translator

from .money import Terms

_ = Translator("Casino", __file__)

log = logging.getLogger("red.vrt.casino.table")

BETTING_WINDOW = 10.0
DECISION_TIME = 35.0
SHOOTER_TIME = 10.0
RESULTS_HOLD = 2.5
# A player who leaves mid-decision keeps their turn this long, in case they're only reconnecting
LEAVE_GRACE = 8.0

# How long the page animates each event. The bot waits this long after sending one, so results never spoil it
PACE = {"flip": 2.0, "shuffle": 3.0, "roll": 2.0, "deal": 0.45, "reveal": 0.6, "burn": 1.2, "pull": 3.0}


class Closed(Exception):
    """The table is closing: the round stops at its next wait and refunds what it hasn't paid"""


@dataclass
class Bet:
    member: t.Any
    amount: int
    terms: Terms  # the payout terms when the stake was taken; a second stake (double, war) keeps them
    choice: t.Any = None
    settled: bool = False
    outcome: str = ""
    payout: int = 0


def player_view(member, bet: Bet | None, away: bool) -> dict:
    return {
        "id": str(member.id),
        "name": member.display_name,
        "avatar": member.display_avatar.url,
        "bet": bet.amount if bet else None,
        "choice": bet.choice if bet else None,
        "outcome": bet.outcome if bet and bet.settled else None,
        "payout": bet.payout if bet and bet.settled else None,
        "away": away,
    }


class Floor:
    """Everyone in one Activity window: who is in the lobby, who is at which table"""

    def __init__(self, cog, room, guild):
        self.cog = cog
        self.room = room
        self.guild = guild
        self.where: dict[t.Any, str | None] = {}
        self.tables: dict[str, "Table"] = {}
        # Once closing, no new table is made, so nothing can start after the close loop has passed it
        self.closing = False

    async def scope(self) -> int:
        return await self.cog.store.scope_for(self.guild.id)

    def table(self, game: str) -> "Table":
        if game not in self.tables:
            if self.closing:
                raise Closed()
            self.tables[game] = self.cog.table_types[game](self, game)
        return self.tables[game]

    def conns_of(self, user_id: int) -> list:
        return [conn for conn in self.where if conn.ctx.author.id == user_id]

    def counts(self) -> dict[str, int]:
        people: dict[str, set[int]] = {}
        for conn, game in self.where.items():
            if game is not None:
                people.setdefault(game, set()).add(conn.ctx.author.id)
        return {game: len(users) for game, users in people.items()}

    async def send_lobby(self) -> None:
        await self.room.broadcast({"t": "lobby", "counts": self.counts()})

    async def arrive(self, conn) -> None:
        self.where[conn] = None
        await self.send_lobby()

    async def enter(self, conn, game: str) -> None:
        if self.closing:
            return
        await self.leave_table(conn)
        self.where[conn] = game
        await self.table(game).enter(conn)
        await self.send_lobby()

    async def to_lobby(self, conn) -> None:
        await self.leave_table(conn)
        self.where[conn] = None
        await self.send_lobby()

    async def depart(self, conn) -> None:
        await self.leave_table(conn)
        self.where.pop(conn, None)
        await self.send_lobby()

    async def leave_table(self, conn) -> None:
        game = self.where.get(conn)
        if game is not None:
            await self.table(game).leave(conn)

    def idle(self) -> bool:
        return not self.where and all(not table.busy() for table in self.tables.values())

    async def close(self) -> None:
        self.closing = True
        for table in list(self.tables.values()):
            try:
                await table.close()
            except Exception as e:
                log.exception("Couldn't close the %s table", table.game, exc_info=e)


class Table:
    """One game's table in one window. Subclasses fill in play() and, when the game has one, read_choice()"""

    def __init__(self, floor: Floor, game: str):
        self.floor = floor
        self.game = game
        self.present: dict[t.Any, t.Any] = {}
        self.bets: dict[int, Bet] = {}
        self.phase = "idle"
        self.round = 0
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.go = asyncio.Event()
        # Closing never cancels a round mid-payout: the round sees this at its next wait and stops there
        self.closing = asyncio.Event()
        self.deadline: float | None = None
        # Players the round is waiting on, and the moves each may send
        self.decisions: dict[int, asyncio.Future] = {}
        self.allowed: dict[int, tuple[str, ...]] = {}
        # The move each waiting player gets if they don't answer
        self.fallbacks: dict[int, str] = {}
        # One leave-grace timer per player who left mid-decision
        self.graces: dict[int, asyncio.TimerHandle] = {}
        # Tests set speed to 0 to skip the animation waits; time limits stay real
        self.speed = 1.0
        self.times = {
            "betting": BETTING_WINDOW,
            "decision": DECISION_TIME,
            "shooter": SHOOTER_TIME,
            "grace": LEAVE_GRACE,
        }

    @property
    def cog(self):
        return self.floor.cog

    # ---------- Who is here ----------

    def users(self) -> set[int]:
        return {member.id for member in self.present.values()}

    def is_here(self, user_id: int) -> bool:
        return user_id in self.users()

    async def enter(self, conn) -> None:
        self.present[conn] = conn.ctx.author
        self.stop_grace(conn.ctx.author.id)
        await self.push()
        # A player who comes back mid-decision gets their buttons again
        if conn.ctx.author.id in self.allowed:
            await conn.send(self.ask_message(conn.ctx.author.id))

    async def leave(self, conn) -> None:
        self.present.pop(conn, None)
        await self.push()
        user_id = conn.ctx.author.id
        if user_id in self.decisions and not self.is_here(user_id):
            self.stop_grace(user_id)
            self.graces[user_id] = asyncio.get_running_loop().call_later(self.times["grace"], self.give_up, user_id)

    def stop_grace(self, user_id: int) -> None:
        timer = self.graces.pop(user_id, None)
        if timer is not None:
            timer.cancel()

    def give_up(self, user_id: int) -> None:
        """A player who left and didn't come back takes their default, so the table doesn't wait out their clock"""
        self.graces.pop(user_id, None)
        future = self.decisions.get(user_id)
        if future is not None and not future.done() and not self.is_here(user_id):
            future.set_result(self.fallbacks[user_id])

    # ---------- Sending ----------

    def state(self) -> dict:
        members = {member.id: member for member in self.present.values()}
        for user_id, bet in self.bets.items():
            members.setdefault(user_id, bet.member)
        here = self.users()
        players = [player_view(m, self.bets.get(uid), uid not in here) for uid, m in members.items()]
        left = None
        if self.deadline is not None:
            left = max(0.0, round(self.deadline - asyncio.get_running_loop().time(), 2))
        return {
            "t": "table",
            "game": self.game,
            "phase": self.phase,
            "round": self.round,
            "left": left,
            "players": players,
            **self.extra_state(),
        }

    def extra_state(self) -> dict:
        return {}

    async def push(self) -> None:
        state = self.state()
        for conn in list(self.present):
            await conn.send(state)

    async def event(self, kind: str, **data) -> None:
        """Something for the page to animate, then a wait while it plays"""
        message = {"t": "event", "game": self.game, "kind": kind, **data}
        for conn in list(self.present):
            await conn.send(message)
        await self.pause(PACE.get(kind, 0.0))

    async def pause(self, seconds: float) -> None:
        await self.wait_on(asyncio.sleep(seconds * self.speed) if seconds * self.speed > 0 else None)

    async def wait_on(self, awaitable, timeout: float | None = None) -> None:
        """Waits for the awaitable (or just checks for closing when it's None), the timeout, or the table closing,
        whichever comes first. Raises Closed when the table is closing"""
        if self.closing.is_set():
            if awaitable is not None and asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise Closed()
        if awaitable is None:
            return
        work = asyncio.ensure_future(awaitable)
        stop = asyncio.ensure_future(self.closing.wait())
        try:
            await asyncio.wait({work, stop}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for future in (work, stop):
                if not future.done():
                    future.cancel()
        if self.closing.is_set():
            raise Closed()

    async def tell(self, user_id: int, message: dict) -> None:
        for conn in self.floor.conns_of(user_id):
            await conn.send(message)

    async def notice(self, conn, text: str) -> None:
        await conn.send({"t": "notice", "text": text})

    # ---------- Betting ----------

    def read_choice(self, data: dict) -> tuple[t.Any, str | None]:
        """The player's call for games that have one, and the problem when it isn't valid"""
        return None, None

    def can_bet(self, user_id: int) -> str | None:
        return None

    async def bet(self, conn, data: dict) -> None:
        member = conn.ctx.author
        amount = data.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            await self.notice(conn, _("Pick an amount to bet."))
            return
        async with self.lock:
            if self.closing.is_set():
                await self.notice(conn, _("This table is closing."))
                return
            if self.phase not in ("idle", "betting"):
                await self.notice(conn, _("Wait for the next round."))
                return
            if member.id in self.bets:
                await self.notice(conn, _("You already bet this round."))
                return
            if problem := self.can_bet(member.id):
                await self.notice(conn, problem)
                return
            choice, choice_problem = self.read_choice(data)
            scope = await self.floor.scope()
            # Read before the stake, so nothing can fail between taking the money and recording the bet
            terms = await self.cog.money.terms(scope, member.id, self.game)
            if problem := await self.cog.money.stake(scope, member, self.game, amount, choice_problem):
                await self.notice(conn, problem)
                return
            self.bets[member.id] = Bet(member, amount, terms, choice)
            await self.cog.send_me(self.floor, member)
            if self.phase == "idle":
                self.phase = "betting"
                self.task = asyncio.create_task(self.run())
        await self.push()

    async def press_go(self, conn) -> None:
        if conn.ctx.author.id in self.bets and self.phase == "betting":
            self.go.set()

    async def move(self, conn, data: dict) -> None:
        user_id = conn.ctx.author.id
        move = data.get("move")
        future = self.decisions.get(user_id)
        if future is not None and not future.done() and move in self.allowed.get(user_id, ()):
            future.set_result(move)

    # ---------- A round ----------

    async def run(self) -> None:
        try:
            if len(self.users()) > 1:
                await self.betting_window()
            # A bet still being staked finishes first, so it joins this round instead of being wiped by its reset
            async with self.lock:
                self.phase = "playing"
                self.round += 1
            await self.push()
            await self.play()
            self.phase = "results"
            await self.push()
            await self.pause(RESULTS_HOLD)
        except Closed as e:
            log.debug("The %s table closed mid-round: %r", self.game, e)
            await self.refund()
        except asyncio.CancelledError as e:
            log.debug("The %s round was cancelled: %r", self.game, e)
            await self.refund()
            raise
        except Exception as e:
            log.error("A %s round failed; refunding its bets", self.game, exc_info=e)
            await self.refund()
        finally:
            self.reset()
        await self.push()
        if self.floor.idle():
            self.cog.floor_done(self.floor)

    async def betting_window(self) -> None:
        loop = asyncio.get_running_loop()
        self.deadline = loop.time() + self.times["betting"]
        await self.push()
        await self.wait_on(self.go.wait(), timeout=self.times["betting"])
        self.deadline = None

    def reset(self) -> None:
        self.bets = {}
        self.phase = "idle"
        self.go.clear()
        self.deadline = None
        self.decisions = {}
        self.allowed = {}
        self.fallbacks = {}
        for user_id in list(self.graces):
            self.stop_grace(user_id)
        self.task = None
        self.after_round()

    def after_round(self) -> None:
        """Subclasses tidy up between rounds"""

    def busy(self) -> bool:
        """True while a round, or anything else that still holds money, is running"""
        return self.task is not None

    async def play(self) -> None:
        raise NotImplementedError

    async def refund(self) -> None:
        # A bet still being staked finishes first, so it is refunded too instead of being added mid-loop
        async with self.lock:
            for bet in list(self.bets.values()):
                if bet.settled:
                    continue
                try:
                    await self.cog.money.give_back(bet.terms.scope, bet.member, bet.amount)
                except Exception as e:
                    log.exception("Couldn't refund %s's bet of %s", bet.member.id, bet.amount, exc_info=e)
                    continue
                bet.settled, bet.outcome = True, "refund"
                await self.tell_refund(bet)

    async def tell_refund(self, bet: Bet) -> None:
        """Tells the player their stake came back. The round is already stopping, so a failed send is only logged"""
        try:
            await self.tell(
                bet.member.id,
                {
                    "t": "notice",
                    "text": _("The round stopped, so your bet of {amount} came back.").format(amount=bet.amount),
                },
            )
            await self.cog.send_me(self.floor, bet.member)
        except Exception as e:
            log.warning("Couldn't tell player %s about their refund", bet.member.id, exc_info=e)

    async def close(self) -> None:
        """Stops the round at its next wait, refunding open bets, and waits for it to finish"""
        self.closing.set()
        # A bet still being staked finishes first, so its round is the one awaited below
        async with self.lock:
            pass
        task = self.task
        if task is None:
            return
        # asyncio.wait never cancels the round, and lets a cancel of close() itself through
        finished, pending = await asyncio.wait({task}, timeout=10)
        if pending:
            log.debug("The %s round didn't stop in time, cancelling it", self.game)
            task.cancel()
            finished, pending = await asyncio.wait({task}, timeout=10)
            if pending:
                log.error("The %s round is stuck and couldn't be cancelled", self.game)

    # ---------- Decisions and results ----------

    def ask_message(self, user_id: int) -> dict:
        return {"t": "ask", "game": self.game, "moves": list(self.allowed[user_id])}

    async def decide(self, user_ids: list[int], allowed: tuple | dict, default: str, limit: float) -> dict:
        """Waits up to limit seconds for each player's move. Players who left, or ran out of time, get the default.
        allowed is the moves everyone may send, or a dict of each player's own moves"""
        loop = asyncio.get_running_loop()
        here = [uid for uid in user_ids if self.is_here(uid)]
        for user_id in here:
            self.decisions[user_id] = loop.create_future()
            self.allowed[user_id] = tuple(allowed[user_id] if isinstance(allowed, dict) else allowed)
            self.fallbacks[user_id] = default
        self.deadline = loop.time() + limit
        await self.push()
        # Only the player hears which buttons they have; everyone sees who the table waits on
        for user_id in here:
            await self.tell(user_id, self.ask_message(user_id))
        if here:
            await self.wait_on(asyncio.wait([self.decisions[uid] for uid in here]), timeout=limit)
        moves = {}
        for user_id in user_ids:
            future = self.decisions.pop(user_id, None)
            self.allowed.pop(user_id, None)
            self.fallbacks.pop(user_id, None)
            moves[user_id] = future.result() if future is not None and future.done() else default
            if future is not None and not future.done():
                future.cancel()
        self.deadline = None
        return moves

    async def settle(self, user_id: int, outcome: str, win_amount: int = 0, give_back: int = 0, returned: int = 0):
        """Pays one player's result and tells them. win_amount is what the multiplier applies to"""
        bet = self.bets[user_id]
        money = self.cog.money
        payout, bonus, held = 0, 0, False
        if win_amount > 0 or outcome == "win":
            paid = await money.win(bet.member, self.game, win_amount, bet.terms, returned=returned)
            payout, bonus, held, balance = paid.total, paid.bonus, paid.held, paid.balance
        else:
            balance = await money.give_back(bet.terms.scope, bet.member, give_back)
            payout = give_back
        bet.settled, bet.outcome, bet.payout = True, outcome, payout
        await self.tell(
            user_id,
            {
                "t": "result",
                "game": self.game,
                "outcome": outcome,
                "stake": bet.amount,
                "payout": payout,
                "bonus": bonus,
                "held": held,
                "returned": returned,
                "balance": balance,
            },
        )
        await self.cog.send_me(self.floor, bet.member)
