"""Each game's table: how its round plays. The rules themselves live in games/, the money in Money"""

import asyncio
import logging
import typing as t

from redbot.core.i18n import Translator

from .games import blackjack, simple
from .games.cards import Deck, hand_total, war_value
from .table import PACE, Bet, Closed, Table, player_view

_ = Translator("Casino", __file__)

log = logging.getLogger("red.vrt.casino.rounds")

SEATS = 5


class QuickTable(Table):
    """A game decided by one draw for the whole table: Coin, Cups, Dice and Hi-Lo"""

    choices: tuple = ()
    choice_problem = ""
    kind = ""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        self.drawn: dict = {}

    def read_choice(self, data: dict) -> tuple[t.Any, str | None]:
        if not self.choices:
            return None, None
        choice = data.get("choice")
        return (choice, None) if choice in self.choices else (None, self.choice_problem)

    def draw(self) -> dict:
        raise NotImplementedError

    def factor(self, choice: t.Any) -> int:
        """What the stake is multiplied by before the game's multiplier: 0 means a loss"""
        raise NotImplementedError

    def extra_state(self) -> dict:
        return {"drawn": self.drawn or None}

    async def play(self) -> None:
        self.drawn = self.draw()
        await self.event(self.kind, **self.drawn)
        for user_id, bet in list(self.bets.items()):
            factor = self.factor(bet.choice)
            if factor:
                await self.settle(user_id, "win", win_amount=bet.amount * factor)
            else:
                await self.settle(user_id, "lose")

    def after_round(self) -> None:
        self.drawn = {}


class CoinTable(QuickTable):
    choices = simple.COIN_SIDES
    choice_problem = _("Call heads or tails.")
    kind = "flip"

    def draw(self) -> dict:
        return {"side": simple.flip(self.cog.rng)}

    def factor(self, choice) -> int:
        return 1 if choice == self.drawn["side"] else 0


class CupsTable(QuickTable):
    choices = simple.CUPS
    choice_problem = _("Pick cup 1, 2 or 3.")
    kind = "shuffle"

    def draw(self) -> dict:
        return {"cup": simple.hide_coin(self.cog.rng)}

    def factor(self, choice) -> int:
        return 1 if choice == self.drawn["cup"] else 0


class DiceTable(QuickTable):
    kind = "roll"

    def draw(self) -> dict:
        return {"dice": list(simple.roll(self.cog.rng))}

    def factor(self, choice) -> int:
        return 1 if simple.dice_wins(tuple(self.drawn["dice"])) else 0


class HiLoTable(QuickTable):
    choices = simple.HILO_CHOICES
    choice_problem = _("Pick low, high or seven.")
    kind = "roll"

    def draw(self) -> dict:
        return {"dice": list(simple.roll(self.cog.rng))}

    def factor(self, choice) -> int:
        return simple.hilo_factor(choice, tuple(self.drawn["dice"]))


class CrapsTable(Table):
    """Everyone who bet rides the same rolls. The shooter presses Roll; the dice pass on after each round"""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        self.order: list[int] = []  # who gets the dice next, in the order players arrived
        self.shooter: int | None = None
        self.point: int | None = None
        self.rolls: list[list[int]] = []

    async def enter(self, conn) -> None:
        if conn.ctx.author.id not in self.order:
            self.order.append(conn.ctx.author.id)
        await super().enter(conn)

    def extra_state(self) -> dict:
        return {
            "shooter": str(self.shooter) if self.shooter else None,
            "point": self.point,
            "rolls": self.rolls,
            "waiting": [str(uid) for uid in self.decisions],
        }

    def next_shooter(self) -> int | None:
        """The first bettor in the rotation who is still here"""
        for user_id in self.order:
            if user_id in self.bets and self.is_here(user_id):
                return user_id
        return None

    async def throw(self) -> tuple[int, int]:
        self.shooter = self.next_shooter()
        if self.shooter is not None:
            await self.decide([self.shooter], ("roll",), "roll", self.times["shooter"])
        dice = simple.roll(self.cog.rng)
        self.rolls.append(list(dice))
        await self.event("roll", dice=list(dice), shooter=str(self.shooter) if self.shooter else None)
        return dice

    async def play(self) -> None:
        result, factor = simple.craps_come_out(sum(await self.throw()))
        if result == "point":
            self.point = sum(self.rolls[-1])
            await self.push()
            hit = sum(await self.throw()) == self.point
            result, factor = ("win", 1) if hit else ("lose", 0)
        for user_id, bet in list(self.bets.items()):
            if result == "win":
                await self.settle(user_id, "win", win_amount=bet.amount * factor)
            else:
                await self.settle(user_id, "lose")

    def after_round(self) -> None:
        # The dice pass to the next player in the rotation
        if self.shooter in self.order:
            self.order.remove(self.shooter)
            self.order.append(self.shooter)
        self.order = [uid for uid in self.order if self.is_here(uid)]
        self.shooter, self.point, self.rolls = None, None, []


class WarTable(Table):
    """Casino War: each player's card against the dealer's one card. A tie chooses war or surrender"""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        self.deck = Deck(self.cog.rng)
        self.dealer: list | None = None
        self.war_dealer: list | None = None
        self.hands: dict[int, dict] = {}

    def extra_state(self) -> dict:
        return {
            "dealer": self.dealer,
            "war_dealer": self.war_dealer,
            "hands": {str(uid): hand for uid, hand in self.hands.items()},
            "waiting": [str(uid) for uid in self.decisions],
            "deck": len(self.deck),
        }

    async def deal(self, to: str) -> list:
        card = list(self.deck.draw())
        await self.event("deal", to=to, card=card)
        return card

    async def play(self) -> None:
        for user_id in self.bets:
            self.hands[user_id] = {"card": await self.deal(str(user_id)), "war_card": None, "status": ""}
        self.dealer = await self.deal("dealer")
        tied = []
        for user_id, bet in list(self.bets.items()):
            hand = self.hands[user_id]
            mine, theirs = war_value(tuple(hand["card"])), war_value(tuple(self.dealer))
            if mine == theirs:
                hand["status"] = "tie"
                tied.append(user_id)
            elif mine > theirs:
                hand["status"] = "win"
                await self.settle(user_id, "win", win_amount=bet.amount)
            else:
                hand["status"] = "lose"
                await self.settle(user_id, "lose")
        if tied:
            await self.ties(tied)

    async def ties(self, tied: list[int]) -> None:
        # Going to war is only offered to players who can cover a second bet
        bank = self.cog.money.bank
        options = {}
        for user_id in tied:
            bet = self.bets[user_id]
            options[user_id] = ("war", "surrender") if await bank.can_spend(bet.member, bet.amount) else ("surrender",)
        moves = await self.decide(tied, options, "surrender", self.times["decision"])
        at_war = []
        for user_id in tied:
            bet = self.bets[user_id]
            if moves[user_id] == "war" and await self.cog.money.extra(bet.terms.scope, bet.member, bet.amount):
                # The war bet is part of the stake now, so a refund covers both
                bet.amount *= 2
                self.hands[user_id]["status"] = "war"
                at_war.append(user_id)
            else:
                self.hands[user_id]["status"] = "surrender"
                await self.settle(user_id, "surrender", give_back=bet.amount // 2)
        if not at_war:
            return
        # Everyone sees who surrendered before the war cards come out
        await self.push()
        self.deck.burn(3)
        await self.event("burn", count=3)
        for user_id in at_war:
            self.hands[user_id]["war_card"] = await self.deal(str(user_id))
        self.war_dealer = await self.deal("dealer")
        for user_id in at_war:
            bet, hand = self.bets[user_id], self.hands[user_id]
            if war_value(tuple(hand["war_card"])) >= war_value(tuple(self.war_dealer)):
                hand["status"] = "win"
                await self.settle(user_id, "win", win_amount=bet.amount // 2, returned=bet.amount // 2)
            else:
                hand["status"] = "lose"
                await self.settle(user_id, "lose")

    def after_round(self) -> None:
        self.dealer, self.war_dealer, self.hands = None, None, {}


class DoubleTable(Table):
    """Everyone rides the same coin. Heads doubles everyone still in, tails takes everything from them"""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        self.flips: list[str] = []
        self.standing: dict[int, dict] = {}

    def extra_state(self) -> dict:
        return {
            "flips": self.flips,
            "standing": {str(uid): row for uid, row in self.standing.items()},
            "waiting": [str(uid) for uid in self.decisions],
        }

    async def play(self) -> None:
        self.standing = {uid: {"amount": bet.amount, "status": "in"} for uid, bet in self.bets.items()}
        while True:
            side = simple.flip(self.cog.rng)
            self.flips.append(side)
            await self.event("flip", side=side)
            still_in = [uid for uid, row in self.standing.items() if row["status"] == "in"]
            if side == "tails":
                for user_id in still_in:
                    self.standing[user_id].update(amount=0, status="lost")
                    await self.settle(user_id, "lose")
                return
            for user_id in still_in:
                self.standing[user_id]["amount"] *= 2
            moves = await self.decide(still_in, ("cashout", "keep"), "cashout", self.times["decision"])
            for user_id in still_in:
                if moves[user_id] == "cashout":
                    self.standing[user_id]["status"] = "out"
                    await self.settle(user_id, "win", win_amount=self.standing[user_id]["amount"])
            if not any(row["status"] == "in" for row in self.standing.values()):
                return
            # Everyone sees who cashed out before the next flip
            await self.push()

    def after_round(self) -> None:
        self.flips, self.standing = [], {}


class BlackjackTable(Table):
    """Up to five seats against one dealer, dealt from one deck. Players act one at a time in seat order"""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        self.deck = Deck(self.cog.rng)
        self.seats: list[t.Any] = [None] * SEATS
        self.standing_up: set[int] = set()
        self.hands: dict[int, dict] = {}
        self.dealer: list[list] = []
        self.hidden = True
        self.turn: int | None = None
        # A seated player who drops between rounds keeps the seat for the leave grace, in case they're reconnecting
        self.seat_graces: dict[int, asyncio.Task] = {}

    def seat_of(self, user_id: int) -> int | None:
        for number, member in enumerate(self.seats):
            if member is not None and member.id == user_id:
                return number
        return None

    def can_bet(self, user_id: int) -> str | None:
        return None if self.seat_of(user_id) is not None else _("Take a seat to bet.")

    async def sit(self, conn, number: t.Any) -> None:
        member = conn.ctx.author
        if not isinstance(number, int) or isinstance(number, bool) or not 0 <= number < SEATS:
            return
        if self.seats[number] is not None:
            await self.notice(conn, _("That seat was just taken."))
            return
        if self.seat_of(member.id) is not None:
            return
        self.seats[number] = member
        self.standing_up.discard(member.id)
        await self.push()

    async def stand(self, conn) -> None:
        user_id = conn.ctx.author.id
        if user_id in self.bets:
            self.standing_up.add(user_id)
        elif (number := self.seat_of(user_id)) is not None:
            self.seats[number] = None
        await self.push()

    def extra_state(self) -> dict:
        seats = [
            None if m is None else {"id": str(m.id), "name": m.display_name, "avatar": m.display_avatar.url}
            for m in self.seats
        ]
        dealer = [None if self.hidden and i == 1 else card for i, card in enumerate(self.dealer)]
        shown = [card for card in dealer if card is not None]
        return {
            "seats": seats,
            "hands": {str(uid): hand for uid, hand in self.hands.items()},
            "dealer": {"cards": dealer, "total": hand_total([tuple(c) for c in shown]) if shown else None},
            "turn": str(self.turn) if self.turn else None,
            "waiting": [str(uid) for uid in self.decisions],
            "deck": len(self.deck),
        }

    def order(self) -> list[int]:
        return [m.id for m in self.seats if m is not None and m.id in self.bets]

    async def deal(self, to: int | None, hidden: bool = False) -> None:
        card = list(self.deck.draw())
        if to is None:
            self.dealer.append(card)
        else:
            hand = self.hands[to]
            hand["cards"].append(card)
            hand["total"] = hand_total([tuple(c) for c in hand["cards"]])
        await self.event("deal", to=str(to) if to else "dealer", card=None if hidden else card)

    async def play(self) -> None:
        order = self.order()
        self.hidden = True
        self.deck.ensure(2 * (len(order) + 1))
        self.hands = {uid: {"cards": [], "total": 0, "status": "playing", "doubled": False} for uid in order}
        for second in (False, True):
            for user_id in order:
                await self.deal(user_id)
            await self.deal(None, hidden=second)
        for user_id in order:
            await self.take_turn(user_id)
        self.turn = None
        self.hidden = False
        await self.event("reveal", card=self.dealer[1])
        for card in blackjack.dealer_play([tuple(c) for c in self.dealer], self.deck):
            self.dealer.append(list(card))
            await self.event("deal", to="dealer", card=list(card))
        await self.push()
        dealer = [tuple(c) for c in self.dealer]
        for user_id in order:
            bet = self.bets[user_id]
            outcome = blackjack.outcome([tuple(c) for c in self.hands[user_id]["cards"]], dealer)
            if outcome == "win":
                await self.settle(user_id, "win", win_amount=bet.amount)
            elif outcome == "push":
                await self.settle(user_id, "push", give_back=bet.amount)
            else:
                await self.settle(user_id, outcome)

    async def take_turn(self, user_id: int) -> None:
        hand = self.hands[user_id]
        if hand["total"] == 21:
            hand["status"] = "blackjack"
            return
        self.turn = user_id
        bet = self.bets[user_id]
        # Double is only offered on the first decision, to a player who can cover a second bet
        can_double = await self.cog.money.bank.can_spend(bet.member, bet.amount)
        while hand["total"] < 21:
            allowed = ("hit", "stay", "double") if can_double else ("hit", "stay")
            move = (await self.decide([user_id], allowed, "stay", self.times["decision"]))[user_id]
            if move == "stay":
                break
            if move == "double":
                can_double = False
                if not await self.double(user_id):
                    continue
                break
            can_double = False
            await self.deal(user_id)
        hand["status"] = "bust" if hand["total"] > 21 else "done"
        await self.push()

    async def double(self, user_id: int) -> bool:
        bet = self.bets[user_id]
        if not await self.cog.money.extra(bet.terms.scope, bet.member, bet.amount):
            await self.tell(user_id, {"t": "notice", "text": _("You can't cover a double.")})
            return False
        bet.amount *= 2
        self.hands[user_id]["doubled"] = True
        await self.deal(user_id)
        return True

    def after_round(self) -> None:
        for number, member in enumerate(self.seats):
            if member is not None and (member.id in self.standing_up or not self.is_here(member.id)):
                self.seats[number] = None
        self.standing_up = set()
        self.hands, self.dealer, self.hidden, self.turn = {}, [], True, None

    async def enter(self, conn) -> None:
        self.stop_seat_grace(conn.ctx.author.id)
        await super().enter(conn)

    async def leave(self, conn) -> None:
        await super().leave(conn)
        user_id = conn.ctx.author.id
        if not self.is_here(user_id) and user_id not in self.bets and self.seat_of(user_id) is not None:
            self.stop_seat_grace(user_id)
            self.seat_graces[user_id] = asyncio.create_task(self.free_seat_later(user_id))

    def stop_seat_grace(self, user_id: int) -> None:
        task = self.seat_graces.pop(user_id, None)
        if task is not None:
            task.cancel()

    async def free_seat_later(self, user_id: int) -> None:
        await asyncio.sleep(self.times["grace"])
        self.seat_graces.pop(user_id, None)
        if self.is_here(user_id) or user_id in self.bets or (number := self.seat_of(user_id)) is None:
            return
        self.seats[number] = None
        try:
            await self.push()
        except Exception as e:
            log.warning("Couldn't show the table after freeing player %s's seat", user_id, exc_info=e)

    async def close(self) -> None:
        for user_id in list(self.seat_graces):
            self.stop_seat_grace(user_id)
        await super().close()


class AllInTable(Table):
    """Solo: each player pulls their own slot machine. Only the player sees their pull"""

    def __init__(self, floor, game):
        super().__init__(floor, game)
        self.pulls: set[asyncio.Task] = set()

    async def bet(self, conn, data: dict) -> None:
        multiplier = data.get("multiplier")
        if not isinstance(multiplier, int) or isinstance(multiplier, bool) or multiplier < 2:
            await self.notice(conn, _("Your multiplier must be 2 or higher."))
            return
        member = conn.ctx.author
        async with self.lock:
            if self.closing.is_set():
                await self.notice(conn, _("This table is closing."))
                return
            if member.id in self.bets:
                await self.notice(conn, _("You already bet this round."))
                return
            scope = await self.floor.scope()
            stake = await self.cog.money.bank.balance(member)
            terms = await self.cog.money.terms(scope, member.id, self.game)
            if problem := await self.cog.money.stake(scope, member, self.game, stake):
                await self.notice(conn, problem)
                return
            bet = Bet(member, stake, terms, multiplier)
            self.bets[member.id] = bet
            # Played out in its own task, so the player's other messages aren't held up while the reels spin
            task = asyncio.create_task(self.pull(conn, bet))
            self.pulls.add(task)
            task.add_done_callback(self.pull_done)
        await self.cog.send_me(self.floor, member)

    def pull_done(self, task: asyncio.Task) -> None:
        self.pulls.discard(task)
        if self.floor.idle():
            self.cog.floor_done(self.floor)

    async def pull(self, conn, bet: Bet) -> None:
        user_id, multiplier = bet.member.id, bet.choice
        try:
            won = simple.allin_wins(self.cog.rng, multiplier)
            await conn.send({"t": "event", "game": self.game, "kind": "pull", "win": won, "multiplier": multiplier})
            await self.pause(PACE["pull"])
            if won:
                await self.settle(user_id, "win", win_amount=bet.amount * multiplier)
            else:
                await self.settle(user_id, "lose")
        except Closed as e:
            log.debug("The all-in pull of %s was stopped by the table closing: %r", user_id, e)
            await self.refund_pull(bet)
        except asyncio.CancelledError as e:
            log.debug("The all-in pull of %s was cancelled: %r", user_id, e)
            await self.refund_pull(bet)
            raise
        except Exception as e:
            log.exception("The all-in pull of %s failed; refunding it", user_id, exc_info=e)
            await self.refund_pull(bet)
        finally:
            if self.bets.get(user_id) is bet:
                del self.bets[user_id]

    async def refund_pull(self, bet: Bet) -> None:
        if bet.settled:
            return
        try:
            await self.cog.money.give_back(bet.terms.scope, bet.member, bet.amount)
        except Exception as e:
            log.exception("Couldn't refund %s's pull of %s", bet.member.id, bet.amount, exc_info=e)
            return
        bet.settled, bet.outcome = True, "refund"
        await self.tell_refund(bet)

    def state(self) -> dict:
        # Each pull is private, so the table only shows who is standing at the machines
        players = [player_view(member, None, False) for member in {m.id: m for m in self.present.values()}.values()]
        return {"t": "table", "game": self.game, "phase": "idle", "round": 0, "left": None, "players": players}

    def busy(self) -> bool:
        return super().busy() or bool(self.pulls)

    async def close(self) -> None:
        # A pull still spinning stops and is refunded, like a round
        self.closing.set()
        # A pull still being staked finishes first, so it is awaited below
        async with self.lock:
            pass
        if not self.pulls:
            return
        finished, pending = await asyncio.wait(list(self.pulls), timeout=10)
        if pending:
            log.debug("%s all-in pulls didn't stop in time, cancelling them", len(pending))
            for task in pending:
                task.cancel()
            await asyncio.wait(pending, timeout=10)


TABLE_TYPES: dict[str, type[Table]] = {
    "allin": AllInTable,
    "blackjack": BlackjackTable,
    "coin": CoinTable,
    "craps": CrapsTable,
    "cups": CupsTable,
    "dice": DiceTable,
    "hilo": HiLoTable,
    "war": WarTable,
    "double": DoubleTable,
}
