"""The page's one-off requests (hub.api): stats, the House rules, memberships, and the settings panel"""

import re
import typing as t

from redbot.core.i18n import Translator

from ..abc import MixinMeta
from .catalog import GAMES, global_bank_needed
from .edits import clean_casino, clean_game, whole
from .info import casino_info, player_stats, tiers
from .memberships import clean_membership, open_tier_warning
from .perms import can_manage
from .store import CASINO_RESETS

_ = Translator("Casino", __file__)

# Discord ids are 17 to 20 digits; whole() stops at 18, which is right for settings but not for ids
ID_PATTERN = re.compile(r"[0-9]{1,20}")


def discord_id(value: t.Any) -> int | None:
    """A Discord id sent by the page, as digits or a number, or None"""
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value > 0 else None
    if isinstance(value, str) and ID_PATTERN.fullmatch(value.strip()):
        return int(value.strip())
    return None


class Actions(MixinMeta):
    def action_handlers(self) -> dict[str, t.Callable]:
        return {
            "profile": self.act_profile,
            "player_stats": self.act_player_stats,
            "rules": self.act_rules,
            "memberships": self.act_memberships,
            "settings": self.act_settings,
            "save_casino": self.act_save_casino,
            "save_game": self.act_save_game,
            "save_membership": self.act_save_membership,
            "delete_membership": self.act_delete_membership,
            "find_players": self.act_find_players,
            "player_card": self.act_player_card,
            "player_update": self.act_player_update,
            "reset_casino": self.act_reset_casino,
            "set_mode": self.act_set_mode,
            "wipe": self.act_wipe,
        }

    async def gate(self, ctx, manage: bool = False, owner: bool = False) -> tuple[int, str | None]:
        """The scope the request works on, or why it can't run"""
        if ctx.guild is None:
            return 0, _("Open the casino in a server.")
        if not self.ready.is_set():
            return 0, _("The casino is still opening. Try again in a moment.")
        if owner and not await self.bot.is_owner(ctx.author):
            return 0, _("Only the bot owner can do that.")
        if manage:
            global_mode = await self.store.global_mode()
            if not await can_manage(self.bot, ctx.author, global_mode):
                return 0, _("Only the bot owner can do that.") if global_mode else _("Only casino admins can do that.")
        return await self.store.scope_for(ctx.guild.id), None

    def find_person(self, ctx, user_id: t.Any, scope: int):
        """A member of this server, or in global mode (scope 0) any user the bot can see"""
        number = discord_id(user_id)
        if number is None:
            return None
        member = ctx.guild.get_member(number)
        return member or (self.bot.get_user(number) if scope == 0 else None)

    # ---------- Everyone ----------

    async def act_profile(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx)
        if problem:
            return {"error": problem}
        return await player_stats(self.store, self.money, scope, ctx.author)

    async def act_player_stats(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx)
        if problem:
            return {"error": problem}
        who = self.find_person(ctx, data.get("user_id"), scope)
        if who is None:
            return {"error": _("That player isn't here.")}
        return await player_stats(self.store, self.money, scope, who)

    async def act_rules(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx)
        if problem:
            return {"error": problem}
        return {**await casino_info(self.store, scope), "currency": await self.bank.currency(ctx.guild)}

    async def act_memberships(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx)
        if problem:
            return {"error": problem}
        return {"tiers": await tiers(self.store, scope, None if scope == 0 else ctx.guild)}

    # ---------- Admins ----------

    async def act_settings(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        roles = (
            [] if scope == 0 else [{"id": str(r.id), "name": r.name} for r in ctx.guild.roles if r.name != "@everyone"]
        )
        return {
            **await casino_info(self.store, scope),
            "owner": await self.bot.is_owner(ctx.author),
            "tiers": await tiers(self.store, scope, None if scope == 0 else ctx.guild),
            "roles": roles,
            "open_tier_warning": open_tier_warning(),
        }

    async def act_save_casino(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        fields, problem = (None, problem) if problem else clean_casino(data)
        if problem or not fields:
            return {"error": problem or _("Nothing to change.")}
        await self.store.save_casino(scope, **fields)
        await self.refresh(scope)
        return await casino_info(self.store, scope)

    async def act_save_game(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        key = data.get("game")
        if key not in GAMES:
            return {"error": _("That isn't one of the casino's games.")}
        row = await self.store.game(scope, key)
        fields, problem = clean_game(key, data, row.min_bet, row.max_bet)
        if problem or not fields:
            return {"error": problem or _("Nothing to change.")}
        await self.store.save_game(scope, key, **fields)
        await self.refresh(scope)
        return await casino_info(self.store, scope)

    async def act_save_membership(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        tier_id = whole(data.get("id")) if data.get("id") is not None else None
        if data.get("id") is not None and tier_id is None:
            return {"error": _("That membership is gone.")}
        # The name check and the save happen under one lock, so two saves can't both take the same name
        async with self.store.lock:
            others = [tier.name for tier in await self.store.memberships(scope) if tier.id != tier_id]
            fields, problem = clean_membership(data, others)
            if problem:
                return {"error": problem}
            if tier_id is not None and await self.store.membership(scope, tier_id) is None:
                return {"error": _("That membership is gone.")}
            await self.store.write_membership(scope, fields, tier_id)
        await self.refresh(scope)
        return {"tiers": await tiers(self.store, scope, None if scope == 0 else ctx.guild)}

    async def act_delete_membership(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        tier_id = whole(data.get("id"))
        if tier_id is None or await self.store.membership(scope, tier_id) is None:
            return {"error": _("That membership is gone.")}
        await self.store.delete_membership(scope, tier_id)
        await self.refresh(scope)
        return {"tiers": await tiers(self.store, scope, None if scope == 0 else ctx.guild)}

    async def act_find_players(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        query = str(data.get("query", "")).strip().lower()
        if not query:
            return {"players": []}
        found = [
            {"id": str(m.id), "name": m.display_name, "username": m.name, "avatar": m.display_avatar.url}
            for m in ctx.guild.members
            if not getattr(m, "bot", False) and (query in m.display_name.lower() or query in m.name.lower())
        ]
        return {"players": found[:10]}

    async def act_player_card(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        who = self.find_person(ctx, data.get("user_id"), scope)
        if who is None:
            return {"error": _("That player isn't here.")}
        return await player_stats(self.store, self.money, scope, who)

    async def act_player_update(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        who = self.find_person(ctx, data.get("user_id"), scope)
        if who is None:
            return {"error": _("That player isn't here.")}
        problem = await self.update_player(scope, who, data.get("op"), data)
        if problem:
            return {"error": problem}
        await self.refresh(scope)
        return await player_stats(self.store, self.money, scope, who)

    async def update_player(self, scope: int, who, op: t.Any, data: dict) -> str | None:
        """Give or revoke a tier, release held winnings, or reset the player. Returns a problem, or None"""
        if op == "assign":
            tier_id = whole(data.get("membership_id"))
            if tier_id is None or not await self.store.assign_membership(scope, who.id, tier_id):
                return _("That membership is gone.")
        elif op == "revoke":
            await self.store.set_membership(scope, who.id, None, by_hand=False)
        elif op == "release":
            return (await self.money.release(scope, who))[1]
        elif op in ("reset_cooldowns", "reset_stats", "reset_all"):
            await self.store.reset_player(scope, who.id, op.removeprefix("reset_"))
        else:
            return _("Unknown change.")
        return None

    async def act_reset_casino(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, manage=True)
        if problem:
            return {"error": problem}
        if data.get("what") not in CASINO_RESETS:
            return {"error": _("Pick what to reset.")}
        await self.store.reset_casino(scope, data["what"])
        await self.refresh(scope)
        return await casino_info(self.store, scope)

    # ---------- Owner ----------

    async def act_set_mode(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, owner=True)
        if problem:
            return {"error": problem}
        on = data.get("global")
        if not isinstance(on, bool):
            return {"error": _("Pick global or server mode.")}
        if on and not await self.bank.is_global():
            return {"error": global_bank_needed("[p]")}
        await self.store.set_global_mode(on)
        await self.refresh()
        return {"global": on}

    async def act_wipe(self, ctx, data: dict) -> dict:
        scope, problem = await self.gate(ctx, owner=True)
        if problem:
            return {"error": problem}
        await self.store.wipe()
        await self.refresh()
        return {"wiped": True}
