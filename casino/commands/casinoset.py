"""[p]casinoset: the original's settings commands. They check and save exactly what the page's settings panel does"""

from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common.catalog import GAME_NAMES, GAMES, game_key, global_bank_needed
from ..common.edits import clean_casino, clean_game
from ..common.money import fmt_seconds
from ..views.choose import confirm
from .checks import manager, ready

_ = Translator("Casino", __file__)


def zero_multiplier() -> str:
    return _("Wait a minute... zero?! Really... I'm a bot and that's more heartless than me! Who hurt you, human?")


def not_a_game() -> str:
    return _("That isn't a game. Pick one of: {games}.").format(games=", ".join(GAMES))


@cog_i18n(_)
class CasinoSetCommands(MixinMeta):
    async def set_scope(self, ctx: commands.Context) -> int:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        await ready(ctx)
        return await self.store.scope_for(ctx.guild.id)

    async def save_casino_field(self, ctx: commands.Context, data: dict) -> bool:
        scope = await self.set_scope(ctx)
        fields, problem = clean_casino(data)
        if problem:
            await ctx.send(problem)
            return False
        await self.store.save_casino(scope, **fields)
        await self.refresh(scope)
        return True

    async def save_game_field(self, ctx: commands.Context, game: str, data: dict) -> str | None:
        """Saves one game setting. Returns the game's key, or None after telling the admin what was wrong"""
        scope = await self.set_scope(ctx)
        key = game_key(game)
        if key is None:
            await ctx.send(not_a_game())
            return None
        row = await self.store.game(scope, key)
        fields, problem = clean_game(key, data, row.min_bet, row.max_bet)
        if problem:
            await ctx.send(problem)
            return None
        await self.store.save_game(scope, key, **fields)
        await self.refresh(scope)
        return key

    @commands.group(name="casinoset")
    @commands.guild_only()
    @manager()
    async def casinoset(self, ctx: commands.Context):
        """Change the casino's settings"""

    @casinoset.command(name="name")
    async def casinoset_name(self, ctx: commands.Context, *, name: str):
        """Set the casino's name (30 characters at most)"""
        if await self.save_casino_field(ctx, {"name": name}):
            await ctx.send(
                _("{admin} set the casino's name to {name}.").format(admin=ctx.author.display_name, name=name)
            )

    @casinoset.command(name="toggle")
    async def casinoset_toggle(self, ctx: commands.Context):
        """Open or close the casino. Closing it stops all games"""
        casino = await self.store.casino(await self.set_scope(ctx))
        if await self.save_casino_field(ctx, {"is_open": not casino.is_open}):
            text = _("{admin} closed the {name} Casino.") if casino.is_open else _("{admin} opened the {name} Casino.")
            await ctx.send(text.format(admin=ctx.author.display_name, name=casino.name))

    @casinoset.command(name="payoutlimit")
    async def casinoset_payoutlimit(self, ctx: commands.Context, limit: int):
        """Set the payout limit: wins above it are held until an admin releases them"""
        if await self.save_casino_field(ctx, {"limit_amount": limit}):
            text = _("{admin} set the payout limit to {amount}.")
            await ctx.send(text.format(admin=ctx.author.display_name, amount=humanize_number(limit)))

    @casinoset.command(name="payouttoggle")
    async def casinoset_payouttoggle(self, ctx: commands.Context):
        """Turn the payout limit on or off"""
        casino = await self.store.casino(await self.set_scope(ctx))
        if await self.save_casino_field(ctx, {"limit_on": not casino.limit_on}):
            if casino.limit_on:
                text = _("{admin} turned the payout limit off.")
            else:
                text = _("{admin} turned the payout limit on.")
            await ctx.send(text.format(admin=ctx.author.display_name))

    @casinoset.command(name="min")
    async def casinoset_min(self, ctx: commands.Context, game: str, minimum: int):
        """Set a game's minimum bet"""
        if key := await self.save_game_field(ctx, game, {"min_bet": minimum}):
            text = _("{admin} set {game}'s minimum bet to {amount}.")
            await ctx.send(
                text.format(admin=ctx.author.display_name, game=GAME_NAMES[key], amount=humanize_number(minimum))
            )

    @casinoset.command(name="max")
    async def casinoset_max(self, ctx: commands.Context, game: str, maximum: int):
        """Set a game's maximum bet"""
        if key := await self.save_game_field(ctx, game, {"max_bet": maximum}):
            text = _("{admin} set {game}'s maximum bet to {amount}.")
            await ctx.send(
                text.format(admin=ctx.author.display_name, game=GAME_NAMES[key], amount=humanize_number(maximum))
            )

    @casinoset.command(name="multiplier")
    async def casinoset_multiplier(self, ctx: commands.Context, game: str, multiplier: float):
        """Set a game's payout multiplier: what a win pays back, stake included"""
        if key := await self.save_game_field(ctx, game, {"multiplier": multiplier}):
            text = _("{admin} set {game}'s multiplier to {number}.").format(
                admin=ctx.author.display_name, game=GAME_NAMES[key], number=multiplier
            )
            await ctx.send(f"{text}\n\n{zero_multiplier()}" if multiplier == 0 else text)

    @casinoset.command(name="cooldown")
    async def casinoset_cooldown(self, ctx: commands.Context, game: str, cooldown: str):
        """Set a game's cooldown, in seconds or as DD:HH:MM:SS"""
        if key := await self.save_game_field(ctx, game, {"cooldown": cooldown}):
            seconds = (await self.store.game(await self.set_scope(ctx), key)).cooldown
            text = _("{admin} set {game}'s cooldown to {time}.")
            await ctx.send(text.format(admin=ctx.author.display_name, game=GAME_NAMES[key], time=fmt_seconds(seconds)))

    @casinoset.command(name="access")
    async def casinoset_access(self, ctx: commands.Context, game: str, access: int):
        """Set the access level a game needs. Memberships give access levels"""
        if key := await self.save_game_field(ctx, game, {"access": access}):
            text = _("{admin} set {game}'s access level to {level}.")
            await ctx.send(text.format(admin=ctx.author.display_name, game=GAME_NAMES[key], level=access))

    @casinoset.command(name="gametoggle")
    async def casinoset_gametoggle(self, ctx: commands.Context, game: str):
        """Open or close one game"""
        key = game_key(game)
        if key is None:
            await ctx.send(not_a_game())
            return
        row = await self.store.game(await self.set_scope(ctx), key)
        if await self.save_game_field(ctx, game, {"is_open": not row.is_open}):
            text = _("{admin} closed {game}.") if row.is_open else _("{admin} opened {game}.")
            await ctx.send(text.format(admin=ctx.author.display_name, game=GAME_NAMES[key]))

    @casinoset.command(name="mode")
    @commands.is_owner()
    async def casinoset_mode(self, ctx: commands.Context):
        """Switch between one casino per server and one global casino. Each mode keeps its own data"""
        await ready(ctx)
        now_global = await self.store.global_mode()
        if now_global:
            question = _("The casino is global. Switch to one casino per server?")
        else:
            question = _("Each server has its own casino. Switch to one global casino for every server?")
        if not await confirm(ctx, question):
            return
        if not now_global and not await self.bank.is_global():
            await ctx.send(global_bank_needed(ctx.clean_prefix))
            return
        await self.store.set_global_mode(not now_global)
        await self.refresh()
        if now_global:
            done = _("Each server now has its own casino. The global casino's data is kept for when you switch back.")
        else:
            done = _("The casino is now global. Each server's data is kept for when you switch back.")
        await ctx.send(done)
