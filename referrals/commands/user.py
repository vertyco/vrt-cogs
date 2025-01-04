import logging
from datetime import datetime
from io import StringIO

import discord
from discord import app_commands
from redbot.core import bank, commands
from redbot.core.bot import Red
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_timedelta

from ..abc import MixinMeta
from ..common import utils
from ..common.checks import ensure_db_connection
from ..db.tables import Referral
from ..views.dynamic_menu import DynamicMenu

log = logging.getLogger("red.vrt.referrals.commands.admin")

_ = Translator("Referrals", __file__)


@app_commands.context_menu(name="Referred By")
@app_commands.guild_only()
async def referredby_context(interaction: discord.Interaction, member: discord.Member):
    if not interaction.guild:
        return await interaction.response.send_message(_("This command can only be used in a server."), ephemeral=True)
    if member.bot:
        return await interaction.response.send_message(_("Bots can't refer users."), ephemeral=True)
    if member.id == interaction.user.id:
        return await interaction.response.send_message(_("You can't refer yourself."), ephemeral=True)
    bot: Red = interaction.client
    cog: MixinMeta = bot.get_cog("Referrals")
    if not cog.db:
        return await interaction.response.send_message(
            _("Database connection is not active, try again later."), ephemeral=True
        )

    await interaction.response.defer(thinking=True)
    settings = await cog.db_utils.get_create_guild(interaction.guild)
    if not settings.enabled:
        return await interaction.followup.send(_("Referral rewards are not enabled for this server."))
    if not settings.referral_reward and not settings.referred_reward:
        return await interaction.followup.send(_("Referral rewards are not configured for this server."))
    if interaction.user.id in settings.initialized_users:
        return await interaction.followup.send(
            _("You were already a part of this server when the referral system was initialized.")
        )
    account_age_minutes = int((datetime.now().astimezone() - interaction.user.created_at).total_seconds() / 60)
    if settings.min_account_age_minutes and account_age_minutes < settings.min_account_age_minutes:
        required_time = humanize_timedelta(seconds=settings.min_account_age_minutes * 60)
        return await interaction.followup.send(
            _("You must have an account age of at least {} to be eligible for referral rewards.").format(
                f"**{required_time}**"
            )
        )
    join_minutes = int((datetime.now().astimezone() - interaction.user.joined_at).total_seconds() / 60)
    if settings.claim_timeout_minutes and join_minutes > settings.claim_timeout_minutes:
        required_time = humanize_timedelta(seconds=settings.claim_timeout_minutes * 60)
        return await interaction.followup.send(
            _("You joined the server too long ago to claim a referral reward. You must claim it within {}.").format(
                f"**{required_time}**"
            )
        )
    existing_referral = await Referral.objects().get(
        (Referral.guild == interaction.guild.id) & (Referral.referred_id == interaction.user.id)
    )
    if existing_referral:
        referrer = await bot.fetch_user(existing_referral.referrer_id)
        return await interaction.followup.send(_("You have already been referred by {}.").format(f"**{referrer}**"))

    currency_name = await bank.get_currency_name(interaction.guild)
    response = StringIO()
    response.write(_("You have been referred by {}!\n").format(f"**{member}**"))
    if settings.referred_reward:
        try:
            await bank.deposit_credits(interaction.user, settings.referred_reward)
        except BalanceTooHigh as e:
            await bank.set_balance(interaction.user, e.max_balance)
        txt = _("-# You have received {} as a reward for being referred!\n").format(
            f"`{settings.referred_reward} {currency_name}`"
        )
        response.write(txt)

    if settings.referral_reward:
        try:
            await bank.deposit_credits(member, settings.referral_reward)
        except BalanceTooHigh as e:
            await bank.set_balance(member, e.max_balance)
        txt = _("-# {} has received {} as a reward for referring you!").format(
            f"`{member}`", f"`{settings.referral_reward} {currency_name}`"
        )
        response.write(txt)

    referral = Referral(
        guild=interaction.guild.id,
        referred_id=interaction.user.id,
        referrer_id=member.id,
    )
    await referral.save()
    await interaction.followup.send(response.getvalue())

    if log_channel := bot.get_channel(settings.referral_channel):
        if not all(
            [
                log_channel.permissions_for(interaction.guild.me).send_messages,
                log_channel.permissions_for(interaction.guild.me).embed_links,
            ]
        ):
            return
        color = await bot.get_embed_color(interaction)
        embed = discord.Embed(
            description=_("{} has been referred by {}").format(
                f"`{interaction.user.name} ({interaction.user.id})`", f"`{member.name} ({member.id})`"
            ),
            timestamp=datetime.now(),
            color=color,
        )
        embed.set_author(name=_("Referral Claimed"), icon_url=interaction.user.display_avatar)
        await log_channel.send(embed=embed)


@cog_i18n(_)
class User(MixinMeta):
    @commands.hybrid_command()
    @commands.guild_only()
    @ensure_db_connection()
    @commands.admin_or_permissions(manage_guild=True)
    async def referredby(self, ctx: commands.Context, referred_by: discord.Member):
        """Claim a referral

        Claim a referral from a user who referred you

        If referral rewards are enabled, you will receive the reward for being referred.
        If referrer rewards are enabled, the person who referred you will also receive a reward.
        """
        if referred_by.id == ctx.author.id:
            return await ctx.send(_("You can't refer yourself."))
        if referred_by.bot:
            return await ctx.send(_("Bots can't refer users."))
        settings = await self.db_utils.get_create_guild(ctx.guild)
        if not settings.enabled:
            return await ctx.send(_("Referral rewards are not enabled for this server."))
        if not settings.referral_reward and not settings.referred_reward:
            return await ctx.send(_("Referral rewards are not configured for this server."))
        if ctx.author.id in settings.initialized_users:
            return await ctx.send(_("You were already a part of this server when the referral system was initialized."))
        account_age_minutes = int((datetime.now().astimezone() - ctx.author.created_at).total_seconds() / 60)
        if settings.min_account_age_minutes and account_age_minutes < settings.min_account_age_minutes:
            required_time = humanize_timedelta(seconds=settings.min_account_age_minutes * 60)
            return await ctx.send(
                _("You must have an account age of at least {} to be eligible for referral rewards.").format(
                    f"**{required_time}**"
                )
            )
        join_minutes = int((datetime.now().astimezone() - ctx.author.joined_at).total_seconds() / 60)
        if settings.claim_timeout_minutes and join_minutes > settings.claim_timeout_minutes:
            required_time = humanize_timedelta(seconds=settings.claim_timeout_minutes * 60)
            return await ctx.send(
                _("You joined the server too long ago to claim a referral reward. You must claim it within {}.").format(
                    f"**{required_time}**"
                )
            )
        existing_referral = await Referral.objects().get(
            (Referral.guild == ctx.guild.id) & (Referral.referred_id == ctx.author.id)
        )
        if existing_referral:
            referrer = await self.bot.fetch_user(existing_referral.referrer_id)
            return await ctx.send(_("You have already been referred by {}.").format(f"**{referrer}**"))

        currency_name = await bank.get_currency_name(ctx.guild)
        response = StringIO()
        response.write(_("You have been referred by {}!\n").format(f"**{referred_by}**"))
        if settings.referred_reward:
            try:
                await bank.deposit_credits(ctx.author, settings.referred_reward)
            except BalanceTooHigh as e:
                await bank.set_balance(ctx.author, e.max_balance)
            txt = _("-# You have received {} as a reward for being referred!\n").format(
                f"`{settings.referred_reward} {currency_name}`"
            )
            response.write(txt)

        if settings.referral_reward:
            try:
                await bank.deposit_credits(referred_by, settings.referral_reward)
            except BalanceTooHigh as e:
                await bank.set_balance(referred_by, e.max_balance)
            txt = _("-# {} has received {} as a reward for referring you!").format(
                f"`{referred_by}`", f"`{settings.referral_reward} {currency_name}`"
            )
            response.write(txt)

        referral = Referral(
            guild=ctx.guild.id,
            referred_id=ctx.author.id,
            referrer_id=referred_by.id,
        )
        await referral.save()
        await ctx.send(response.getvalue())

        if log_channel := self.bot.get_channel(settings.referral_channel):
            if not all(
                [
                    log_channel.permissions_for(ctx.guild.me).send_messages,
                    log_channel.permissions_for(ctx.guild.me).embed_links,
                ]
            ):
                return

            color = await self.bot.get_embed_color(ctx)
            embed = discord.Embed(
                description=_("{} has been referred by {}").format(
                    f"`{ctx.author.name} ({ctx.author.id})`", f"`{referred_by.name} ({referred_by.id})`"
                ),
                timestamp=datetime.now(),
                color=color,
            )
            embed.set_author(name=_("Referral Claimed"), icon_url=ctx.author.display_avatar)
            await log_channel.send(embed=embed)

    @commands.hybrid_command()
    @commands.guild_only()
    @ensure_db_connection()
    async def myreferrals(self, ctx: commands.Context):
        """Check your referrals"""
        referrals = await Referral.objects().where(
            (Referral.guild == ctx.guild.id) & (Referral.referrer_id == ctx.author.id)
        )
        if not referrals:
            return await ctx.send(_("You have not referred anyone yet."))
        color = await self.bot.get_embed_color(ctx)
        embeds = []
        chunk_size = 5
        for idx, chunk in enumerate(utils.chunk(referrals, chunk_size)):
            txt = StringIO()
            for idxx, referral in enumerate(chunk, start=idx):
                referred_user = await self.bot.get_or_fetch_user(referral.referred_id)
                txt.write(f"{idxx + 1}. {referred_user}\n")
            embed = discord.Embed(title=_("Your Referrals"), description=txt.getvalue(), color=color)
            embed.set_footer(text=_("Page {}/{}").format(idx + 1, len(referrals)))
            embeds.append(embed)
        await DynamicMenu(ctx, embeds).refresh()

    @commands.hybrid_command()
    @commands.guild_only()
    @ensure_db_connection()
    async def whoreferred(self, ctx: commands.Context, user: discord.Member):
        """Check if a specific user has been referred"""
        referral = await Referral.objects().get((Referral.guild == ctx.guild.id) & (Referral.referred_id == user.id))
        if not referral:
            return await ctx.send(_("{} has not been referred by anyone.").format(user))

        referrer = await self.bot.get_or_fetch_user(referral.referrer_id)
        await ctx.send(_("{} was referred by {}.").format(user, referrer))
