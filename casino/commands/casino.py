"""[p]casino: open the casino, read stats, rules and memberships, and manage players. /casino opens it directly"""

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common.catalog import CREDIT
from ..common.info import casino_info, player_stats, tiers
from ..views.choose import ask, confirm
from ..views.tiers import Designer, TierReader
from .checks import manager, ready
from .embeds import info_embed, stats_embed

_ = Translator("Casino", __file__)


def player_resets() -> list[tuple[str, str]]:
    return [("cooldowns", _("Cooldowns")), ("stats", _("Stats")), ("all", _("Everything"))]


def casino_resets() -> list[tuple[str, str]]:
    return [
        ("settings", _("Settings")),
        ("games", _("Games")),
        ("cooldowns", _("Cooldowns")),
        ("memberships", _("Memberships")),
        ("all", _("All four")),
    ]


@cog_i18n(_)
class CasinoCommands(MixinMeta):
    async def scope_of(self, ctx: commands.Context) -> int:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        await ready(ctx)
        return await self.store.scope_for(ctx.guild.id)

    def tier_guild(self, ctx: commands.Context, scope: int):
        # Roles only mean something in server mode
        return None if scope == 0 else ctx.guild

    @commands.group(name="casino", invoke_without_command=True)
    @commands.guild_only()
    async def casino_group(self, ctx: commands.Context):
        """Open the casino. The subcommands show stats, rules and memberships"""
        casino = await self.store.casino(await self.scope_of(ctx))
        if casino.is_open:
            text = _("**{name} Casino** is open. Press to play:").format(name=casino.name)
        else:
            text = _("**{name} Casino** is closed right now.").format(name=casino.name)
        await ctx.send(text, view=self.play_view)

    @app_commands.command(name="casino", description=_("Open the casino"))
    @app_commands.guild_only()
    async def casino_slash(self, interaction: discord.Interaction):
        hub = self.bot.get_cog("ActivityHub")
        if hub is None:
            await interaction.response.send_message(_("The casino needs the ActivityHub cog."), ephemeral=True)
            return
        await hub.launch(interaction, "casino")

    @casino_group.command(name="stats")
    async def casino_stats(self, ctx: commands.Context, *, player: discord.Member | None = None):
        """Show your casino stats, or another player's"""
        scope = await self.scope_of(ctx)
        stats = await player_stats(self.store, self.money, scope, player or ctx.author)
        await ctx.send(embed=stats_embed(stats, (await self.store.casino(scope)).name))

    @casino_group.command(name="info")
    async def casino_info_command(self, ctx: commands.Context):
        """Show every game's settings: open, access, bets, payout and cooldown"""
        await ctx.send(embed=info_embed(await casino_info(self.store, await self.scope_of(ctx))))

    @casino_group.command(name="memberships")
    async def casino_memberships(self, ctx: commands.Context):
        """Show the membership tiers"""
        scope = await self.scope_of(ctx)
        shown = await tiers(self.store, scope, self.tier_guild(ctx, scope))
        if not shown:
            await ctx.send(_("There are no memberships to display."))
            return
        view = TierReader(ctx.author.id, shown)
        view.message = await ctx.send(_("Which membership would you like to know more about?"), view=view)

    @casino_group.command(name="version")
    async def casino_version(self, ctx: commands.Context):
        """Show the casino's version"""
        await ctx.send(_("Casino is running version {version}.").format(version=self.__version__) + "\n" + CREDIT)

    # ---------- Admins ----------

    @casino_group.command(name="releasecredits")
    @manager()
    async def casino_releasecredits(self, ctx: commands.Context, *, player: discord.Member):
        """Release a player's winnings held by the payout limit"""
        scope = await self.scope_of(ctx)
        pending = (await self.store.player(scope, player.id)).pending
        if pending <= 0:
            await ctx.send(_("They don't have any credits pending."))
            return
        currency = await self.bank.currency(ctx.guild)
        question = _("{player} has {amount} {currency} pending. Release them?")
        if not await confirm(
            ctx, question.format(player=player.display_name, amount=humanize_number(pending), currency=currency)
        ):
            return
        amount, problem = await self.money.release(scope, player)
        await self.refresh(scope)
        if problem:
            await ctx.send(problem)
            return
        await ctx.send(
            _("{player}, your pending {amount} {currency} were approved by {admin} and deposited.").format(
                player=player.mention, amount=humanize_number(amount), currency=currency, admin=ctx.author.display_name
            ),
            allowed_mentions=discord.AllowedMentions(users=[player]),
        )

    @casino_group.command(name="resetuser")
    @manager()
    async def casino_resetuser(self, ctx: commands.Context, *, player: discord.Member):
        """Reset a player's cooldowns, stats, or everything"""
        scope = await self.scope_of(ctx)
        question = _("What should be reset for {player}?").format(player=player.display_name)
        what = await ask(ctx, question, player_resets(), danger=("all",))
        if what is None:
            return
        await self.store.reset_player(scope, player.id, what)
        await self.refresh(scope)
        text = _("{admin} reset {player}: {what}.")
        await ctx.send(
            text.format(admin=ctx.author.display_name, player=player.display_name, what=dict(player_resets())[what])
        )

    @casino_group.command(name="resetinstance")
    @manager()
    async def casino_resetinstance(self, ctx: commands.Context):
        """Reset the casino's settings, games, cooldowns, memberships, or all four. Players' stats stay"""
        scope = await self.scope_of(ctx)
        what = await ask(ctx, _("What should be reset?"), casino_resets(), danger=("all",))
        if what is None:
            return
        await self.store.reset_casino(scope, what)
        await self.refresh(scope)
        text = _("{admin} reset the casino: {what}.")
        await ctx.send(text.format(admin=ctx.author.display_name, what=dict(casino_resets())[what]))

    @casino_group.command(name="assignmem")
    @manager()
    async def casino_assignmem(self, ctx: commands.Context, player: discord.Member, *, membership: str):
        """Give a player a membership by hand. It stays until it is revoked"""
        scope = await self.scope_of(ctx)
        tier = await self.store.membership_named(scope, membership)
        if tier is None:
            await ctx.send(_("{name} is not a membership here.").format(name=membership))
            return
        if not await self.store.assign_membership(scope, player.id, tier.id):
            await ctx.send(_("{name} is not a membership here.").format(name=membership))
            return
        await self.refresh(scope)
        await ctx.send(
            _("{admin} gave {player} the {name} membership.").format(
                admin=ctx.author.display_name, player=player.display_name, name=tier.name
            )
        )

    @casino_group.command(name="revokemem")
    @manager()
    async def casino_revokemem(self, ctx: commands.Context, *, player: discord.Member):
        """Take back a player's membership, given by hand or not. The next automatic update re-checks the player"""
        scope = await self.scope_of(ctx)
        await self.store.set_membership(scope, player.id, None, by_hand=False)
        await self.refresh(scope)
        await ctx.send(_("{player} is Basic until the next membership update.").format(player=player.display_name))

    @casino_group.command(name="memdesigner")
    @manager()
    async def casino_memdesigner(self, ctx: commands.Context):
        """Make, change or delete membership tiers"""
        scope = await self.scope_of(ctx)
        guild = self.tier_guild(ctx, scope)
        shown = await tiers(self.store, scope, guild)
        view = Designer(self, ctx.author.id, scope, guild, shown)
        view.message = await ctx.send(_("Make a new membership, or pick one to change or delete."), view=view)

    # ---------- Owner ----------

    @casino_group.command(name="wipe")
    @commands.is_owner()
    async def casino_wipe(self, ctx: commands.Context):
        """Delete all casino data: every server's settings, memberships and players"""
        await ready(ctx)
        if not await confirm(ctx, _("This deletes all casino data in every server, including players. Are you sure?")):
            return
        await self.store.wipe()
        await self.refresh()
        await ctx.send(_("{admin} wiped all casino data.").format(admin=ctx.author.display_name))
