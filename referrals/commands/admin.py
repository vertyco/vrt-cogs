import logging
import typing as t
from io import StringIO

import discord
from redbot.core import bank, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_timedelta

from ..abc import MixinMeta
from ..common import utils
from ..common.checks import ensure_db_connection
from ..db.tables import GuildSettings, Referral
from ..views.dynamic_menu import DynamicMenu

log = logging.getLogger("red.vrt.referrals.commands.admin")

_ = Translator("Referrals", __file__)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.group(aliases=["refset", "referralset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def referset(self, ctx: commands.Context):
        """Settings for the referral system"""
        pass

    @referset.command()
    @ensure_db_connection()
    async def view(self, ctx: commands.Context):
        """View the current settings for the guild"""
        settings = await self.db_utils.get_create_guild(ctx.guild)
        currency_name = await bank.get_currency_name(ctx.guild)
        title = _("Referral System Settings")
        embed = discord.Embed(title=title, color=await ctx.embed_color())
        embed.add_field(
            name=_("Status"),
            value=_("`Enabled`") if settings.enabled else _("`Disabled`"),
            inline=False,
        )
        embed.add_field(
            name=_("Referral Reward"),
            value=_("Amount of {} given to the person who referred someone: {}").format(
                currency_name, f"`{settings.referral_reward}`"
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Referred Reward"),
            value=_("Amount of {} given to the person who was referred: {}").format(
                currency_name, f"`{settings.referred_reward}`"
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Referral Log"),
            value=_("Channel where referral events are sent: {}").format(
                f"<#{settings.referral_channel}>" if settings.referral_channel else _("`Not set`")
            ),
            inline=False,
        )
        min_age = humanize_timedelta(seconds=settings.min_account_age_minutes * 60)
        embed.add_field(
            name=_("Minimum Account Age"),
            value=_("Account of referred user must be at least {} old to make the claim.").format(f"`{min_age}`")
            if settings.min_account_age_minutes
            else _("There is no minimum account age requirement for users to claim their referral"),
            inline=False,
        )
        claim_timeout = humanize_timedelta(seconds=settings.claim_timeout_minutes * 60)
        embed.add_field(
            name=_("Claim Timeout"),
            value=_("Referral claims must be done within {} after joining.").format(f"`{claim_timeout}`")
            if settings.claim_timeout_minutes
            else _("Users have no time limit to claim their referral"),
            inline=False,
        )
        embed.add_field(
            name=_("Initialized Users"),
            value=_("Users who have been initialized: {}").format(f"`{len(settings.initialized_users)}`"),
            inline=False,
        )
        embed.add_field(
            name=_("Referrals Claimed"),
            value=_("Total referrals claimed: {}").format(
                f"`{await Referral.count().where(Referral.guild == ctx.guild.id)}`"
            ),
        )
        await ctx.send(embed=embed)

    @referset.command()
    @ensure_db_connection()
    async def listreferrals(self, ctx: commands.Context):
        """List all referrals made in the server"""
        referrals = await Referral.objects().where(Referral.guild == ctx.guild.id)
        if not referrals:
            return await ctx.send(_("No referrals found in this server"))
        color = await self.bot.get_embed_color(ctx)
        embeds = []
        chunk_size = 5
        for idx, chunk in enumerate(utils.chunk(referrals, chunk_size)):
            txt = StringIO()
            for idxx, referral in enumerate(chunk, start=idx):
                referrer = await self.bot.get_or_fetch_user(referral.referrer_id)
                referred = await self.bot.get_or_fetch_user(referral.referred_id)
                txt.write(f"{idxx + 1}. {referred} referred by {referrer}\n")
            embed = discord.Embed(title=_("Referrals"), description=txt.getvalue(), color=color)
            embed.set_footer(text=_("Page {}/{}").format(idx + 1, len(referrals)))
            embeds.append(embed)
        await DynamicMenu(ctx, embeds).refresh()

    @referset.command()
    @ensure_db_connection()
    async def toggle(self, ctx: commands.Context):
        """Toggle the referral system on or off"""
        settings = await self.db_utils.get_create_guild(ctx.guild)
        settings.enabled = not settings.enabled
        await settings.save()
        await ctx.send(_("Referral system is now {}").format(_("enabled") if settings.enabled else _("disabled")))

    @referset.command()
    @ensure_db_connection()
    async def reward(self, ctx: commands.Context, reward_type: t.Literal["referral", "referred"], amount: int):
        """Set the reward for referring or being referred

        **Arguments:**
        - `reward_type` - Either `referral` or `referred`
          - `referral` - The reward for referring someone
          - `referred` - The reward for being referred
        - `amount` - The amount of currency to reward

        *Set to 0 to disable the reward*
        """
        settings = await self.db_utils.get_create_guild(ctx.guild)
        currency_name = await bank.get_currency_name(ctx.guild)
        if reward_type == "referral":
            settings.referral_reward = amount
            txt = _("The person who referred someone will receive {}").format(f"`{amount} {currency_name}`")
        elif reward_type == "referred":
            settings.referred_reward = amount
            txt = _("The person who was referred will receive {}").format(f"`{amount} {currency_name}`")
        else:
            return await ctx.send_help()
        await settings.save([GuildSettings.referral_reward, GuildSettings.referred_reward])
        await ctx.send(txt)

    @referset.command()
    @ensure_db_connection()
    async def channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel where referral events will be sent"""
        settings = await self.db_utils.get_create_guild(ctx.guild)
        if not channel and not settings.referral_channel:
            return await ctx.send(_("Referral events are not being sent to any channel"))
        settings.referral_channel = channel.id if channel else 0
        await settings.save([GuildSettings.referral_channel])
        if channel:
            if not channel.permissions_for(ctx.me).send_messages:
                return await ctx.send(_("I don't have permission to send messages in that channel"))
            if not channel.permissions_for(ctx.me).embed_links:
                return await ctx.send(_("I don't have permission to send embeds in that channel"))
            await ctx.send(_("Referral events will be sent to {}").format(channel.mention))
        else:
            await ctx.send(_("Referral events will no longer be sent to a channel"))

    @referset.command()
    @ensure_db_connection()
    async def age(self, ctx: commands.Context, age: str):
        """Set the minimum account age for referred users to be eligible for rewards

        - `age` - The minimum account age in the format of `30m`, `1h`, `2d12h`, etc.
        """
        settings = await self.db_utils.get_create_guild(ctx.guild)
        if "none" in age.lower():
            delta = None
        else:
            try:
                delta = commands.parse_timedelta(age)
            except ValueError:
                delta = None

        if delta is None:
            settings.min_account_age_minutes = 0
            txt = _("Account age restriction removed")
        else:
            settings.min_account_age_minutes = int(delta.total_seconds() / 60)
            txt = _("The minimum account age required to claim a referral is {}").format(
                f"`{humanize_timedelta(timedelta=delta)}`"
            )
        await settings.save([GuildSettings.min_account_age_minutes])
        await ctx.send(txt)

    @referset.command()
    @ensure_db_connection()
    async def timeout(self, ctx: commands.Context, timeout: str):
        """Set the time frame for users to claim their reward after joining

        - `timeout` - The time frame in the format of `30m`, `1h`, `2d12h`, etc.
        """
        settings = await self.db_utils.get_create_guild(ctx.guild)
        if "none" in timeout.lower():
            delta = None
        else:
            try:
                delta = commands.parse_timedelta(timeout)
            except ValueError:
                delta = None

        if delta is None:
            settings.claim_timeout_minutes = 0
            txt = _("Claim timeout removed")
        else:
            settings.claim_timeout_minutes = int(delta.total_seconds() / 60)
            txt = _("Users will have {} to claim their referral after joining.").format(
                f"`{humanize_timedelta(timedelta=delta)}`"
            )
        await settings.save([GuildSettings.claim_timeout_minutes])
        await ctx.send(txt)

    @referset.command(aliases=["initialize"])
    @ensure_db_connection()
    async def init(self, ctx: commands.Context):
        """Initialize all unreferred users in the server so they cannot retroactively claim rewards"""
        settings = await self.db_utils.get_create_guild(ctx.guild)
        referrals: list[int] = (
            await Referral.select(Referral.referred_id).where(Referral.guild == ctx.guild.id).output(as_list=True)
        )
        guild_members: list[int] = [member.id for member in ctx.guild.members]
        unreferred = list(set(guild_members) - set(referrals))
        if not unreferred:
            return await ctx.send(_("All users have been initialized"))
        new_refs = list(set(unreferred + settings.initialized_users))
        settings.initialized_users = new_refs
        await GuildSettings.raw(
            "UPDATE guild_settings SET initialized_users = {} WHERE id = {}", new_refs, ctx.guild.id
        )
        await ctx.send(_("Initialized {} users").format(len(unreferred)))

    @referset.command()
    @ensure_db_connection()
    async def resetall(self, ctx: commands.Context, confirm: bool):
        """Reset all referral data and settings for the guild

        This deletes all referrals and settings, completely starting fresh.
        """
        if not confirm:
            return await ctx.send(_("Rerun this with `True` to comfirm"))
        await Referral.delete().where(Referral.guild == ctx.guild.id)
        await GuildSettings.delete().where(GuildSettings.id == ctx.guild.id)
        await ctx.send(_("All referral data has been reset for this server"))

    @referset.command()
    @ensure_db_connection()
    async def resetreferrals(self, ctx: commands.Context, confirm: bool):
        """Reset all referral records for the guild

        This keeps your settings but removes all referral history.
        """
        if not confirm:
            return await ctx.send(_("Rerun this with `True` to confirm"))
        await Referral.delete().where(Referral.guild == ctx.guild.id)
        await ctx.send(_("All referral data has been reset for this server"))

    @referset.command()
    @ensure_db_connection()
    async def resetsettings(self, ctx: commands.Context, confirm: bool):
        """Reset all referral settings for the guild

        This keeps your referral history but resets all configuration settings.
        """
        if not confirm:
            return await ctx.send(_("Rerun this with `True` to confirm"))
        await GuildSettings.delete().where(GuildSettings.id == ctx.guild.id)
        await ctx.send(_("All referral settings have been reset for this server"))

    @referset.command()
    @ensure_db_connection()
    async def resetinitialized(self, ctx: commands.Context, confirm: bool):
        """Reset the list of initialized users for the guild

        This clears the record of which users have been initialized, allowing them
        to potentially claim referrals.
        """
        if not confirm:
            return await ctx.send(_("Rerun this with `True` to confirm"))
        settings = await self.db_utils.get_create_guild(ctx.guild)
        settings.initialized_users = []
        await settings.save([GuildSettings.initialized_users])
        await ctx.send(_("All initialized users have been reset for this server"))
