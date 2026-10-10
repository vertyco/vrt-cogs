"""Every database read and write the casino makes. Rows are made the first time they're needed, with the defaults"""

import asyncio

from ..db.tables import BotState, CasinoSettings, GameSettings, Membership, Player, PlayerGame
from .catalog import CASINO_DEFAULTS, GAME_DEFAULTS, GAMES

PLAYER_RESETS = ("cooldowns", "stats", "all")
CASINO_RESETS = ("settings", "games", "cooldowns", "memberships", "all")


class Store:
    def __init__(self):
        # Making a row is a read then a write; this stops two requests making the same row twice
        self.lock = asyncio.Lock()

    # ---------- Global mode ----------

    async def global_mode(self) -> bool:
        row = await BotState.objects().where(BotState.id == 1).first()
        return bool(row and row.global_mode)

    async def set_global_mode(self, on: bool) -> None:
        async with self.lock:
            if await BotState.exists().where(BotState.id == 1):
                await BotState.update({BotState.global_mode: on}).where(BotState.id == 1)
            else:
                await BotState.insert(BotState(id=1, global_mode=on))

    async def scope_for(self, guild_id: int) -> int:
        return 0 if await self.global_mode() else guild_id

    # ---------- Casino settings ----------

    async def casino(self, scope: int) -> CasinoSettings:
        row = await CasinoSettings.objects().where(CasinoSettings.id == scope).first()
        if row is not None:
            return row
        async with self.lock:
            row = await CasinoSettings.objects().where(CasinoSettings.id == scope).first()
            if row is None:
                row = CasinoSettings(id=scope, **CASINO_DEFAULTS)
                await row.save()
        return row

    async def save_casino(self, scope: int, **fields) -> CasinoSettings:
        row = await self.casino(scope)
        for name, value in fields.items():
            setattr(row, name, value)
        await row.save()
        return row

    # ---------- Game settings ----------

    async def games(self, scope: int) -> dict[str, GameSettings]:
        rows = {row.game: row for row in await GameSettings.objects().where(GameSettings.scope == scope)}
        if len(rows) == len(GAMES):
            return {key: rows[key] for key in GAMES}
        async with self.lock:
            rows = {row.game: row for row in await GameSettings.objects().where(GameSettings.scope == scope)}
            for key in GAMES:
                if key not in rows:
                    row = GameSettings(scope=scope, game=key, is_open=True, **GAME_DEFAULTS[key])
                    await row.save()
                    rows[key] = row
        return {key: rows[key] for key in GAMES}

    async def game(self, scope: int, key: str) -> GameSettings:
        return (await self.games(scope))[key]

    async def save_game(self, scope: int, key: str, **fields) -> GameSettings:
        row = await self.game(scope, key)
        for name, value in fields.items():
            setattr(row, name, value)
        await row.save()
        return row

    # ---------- Players ----------

    async def player(self, scope: int, user_id: int) -> Player:
        where = (Player.scope == scope) & (Player.user_id == user_id)
        row = await Player.objects().where(where).first()
        if row is not None:
            return row
        async with self.lock:
            row = await Player.objects().where(where).first()
            if row is None:
                row = Player(scope=scope, user_id=user_id, membership=None, by_hand=False, pending=0)
                await row.save()
        return row

    async def players(self, scope: int) -> list[Player]:
        return await Player.objects().where(Player.scope == scope)

    async def player_games(self, scope: int, user_id: int) -> dict[str, PlayerGame]:
        where = (PlayerGame.scope == scope) & (PlayerGame.user_id == user_id)
        rows = {row.game: row for row in await PlayerGame.objects().where(where)}
        if len(rows) == len(GAMES):
            return {key: rows[key] for key in GAMES}
        async with self.lock:
            rows = {row.game: row for row in await PlayerGame.objects().where(where)}
            for key in GAMES:
                if key not in rows:
                    row = PlayerGame(scope=scope, user_id=user_id, game=key, played=0, won=0, ready_at=0.0)
                    await row.save()
                    rows[key] = row
        return {key: rows[key] for key in GAMES}

    async def player_game(self, scope: int, user_id: int, key: str) -> PlayerGame:
        return (await self.player_games(scope, user_id))[key]

    async def add_pending(self, scope: int, user_id: int, amount: int) -> int:
        row = await self.player(scope, user_id)
        await Player.update({Player.pending: Player.pending + amount}).where(Player.id == row.id)
        return (await Player.objects().where(Player.id == row.id).first()).pending

    async def set_membership(self, scope: int, user_id: int, membership_id: int | None, by_hand: bool) -> None:
        row = await self.player(scope, user_id)
        row.membership = membership_id
        row.by_hand = by_hand
        await row.save([Player.membership, Player.by_hand])

    # ---------- Memberships ----------

    async def memberships(self, scope: int) -> list[Membership]:
        return await Membership.objects().where(Membership.scope == scope).order_by(Membership.id)

    async def membership(self, scope: int, membership_id: int) -> Membership | None:
        where = (Membership.scope == scope) & (Membership.id == membership_id)
        return await Membership.objects().where(where).first()

    async def membership_named(self, scope: int, name: str) -> Membership | None:
        for row in await self.memberships(scope):
            if row.name.lower() == name.strip().lower():
                return row
        return None

    async def save_membership(self, scope: int, fields: dict, membership_id: int | None = None) -> Membership:
        """Make a new membership, or change one. The caller checked the fields"""
        async with self.lock:
            return await self.write_membership(scope, fields, membership_id)

    async def write_membership(self, scope: int, fields: dict, membership_id: int | None = None) -> Membership:
        """save_membership for a caller that already holds the lock"""
        if membership_id is None:
            row = Membership(scope=scope, **fields)
        else:
            found = await self.membership(scope, membership_id)
            if found is None:
                raise LookupError(f"No membership {membership_id} in scope {scope}")
            row = found
            for name, value in fields.items():
                setattr(row, name, value)
        await row.save()
        return row

    async def assign_membership(self, scope: int, user_id: int, membership_id: int) -> bool:
        """Give a player a membership by hand. False when the membership is gone"""
        # Nothing inside the lock may call a helper that takes the lock again, so the player row is read directly
        async with self.lock:
            if await self.membership(scope, membership_id) is None:
                return False
            where = (Player.scope == scope) & (Player.user_id == user_id)
            row = await Player.objects().where(where).first()
            if row is None:
                await Player(scope=scope, user_id=user_id, membership=membership_id, by_hand=True, pending=0).save()
            else:
                row.membership = membership_id
                row.by_hand = True
                await row.save([Player.membership, Player.by_hand])
            return True

    async def delete_membership(self, scope: int, membership_id: int) -> None:
        # Its players go back to Basic, and the updater may give them another tier
        async with self.lock:
            await Player.update({Player.membership: None, Player.by_hand: False}).where(
                (Player.scope == scope) & (Player.membership == membership_id)
            )
            await Membership.delete().where((Membership.scope == scope) & (Membership.id == membership_id))

    async def scopes_with_memberships(self) -> list[int]:
        rows = await Membership.select(Membership.scope).distinct()
        return [row["scope"] for row in rows]

    # ---------- Resets ----------

    async def reset_player(self, scope: int, user_id: int, what: str) -> None:
        where = (PlayerGame.scope == scope) & (PlayerGame.user_id == user_id)
        if what == "cooldowns":
            await PlayerGame.update({PlayerGame.ready_at: 0.0}).where(where)
        elif what == "stats":
            await PlayerGame.update({PlayerGame.played: 0, PlayerGame.won: 0}).where(where)
        elif what == "all":
            await PlayerGame.delete().where(where)
            await Player.delete().where((Player.scope == scope) & (Player.user_id == user_id))
        else:
            raise ValueError(f"Unknown player reset: {what}")

    async def reset_casino(self, scope: int, what: str) -> None:
        """The original's resetinstance. Players' stats always stay"""
        if what not in CASINO_RESETS:
            raise ValueError(f"Unknown casino reset: {what}")
        if what in ("settings", "all"):
            await CasinoSettings.delete().where(CasinoSettings.id == scope)
        if what in ("games", "all"):
            await GameSettings.delete().where(GameSettings.scope == scope)
        if what in ("cooldowns", "all"):
            await PlayerGame.update({PlayerGame.ready_at: 0.0}).where(PlayerGame.scope == scope)
        if what in ("memberships", "all"):
            async with self.lock:
                await Player.update({Player.membership: None, Player.by_hand: False}).where(Player.scope == scope)
                await Membership.delete().where(Membership.scope == scope)

    async def wipe(self) -> None:
        """Everything, in every scope, including global mode"""
        for table in (PlayerGame, Player, Membership, GameSettings, CasinoSettings, BotState):
            await table.delete(force=True)

    async def delete_user(self, user_id: int) -> None:
        await PlayerGame.delete().where(PlayerGame.user_id == user_id)
        await Player.delete().where(Player.user_id == user_id)
