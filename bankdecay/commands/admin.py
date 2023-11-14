import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.models import User

_ = Translator("BankDecay", __file__)


class Admin(MixinMeta):
    @commands.group(aliases=["bdecay"])
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def bankdecay(self, ctx: commands.Context):
        """
        Setup economy credit decay for your server
        """
        pass

    @bankdecay.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """View Bank Decay Settings"""
        conf = self.db.get_conf(ctx.guild)
        ignored_roles = [f"<@&{i}>" for i in conf.ignored_roles]
        txt = _(
            "`Decay Enabled: `{}\n"
            "`Inactive Days: `{}\n"
            "`Percent Decay: `{}\n"
            "`Saved Users:   `{}\n"
            "`Total Decayed: `{}\n"
        ).format(
            conf.enabled,
            conf.inactive_days,
            round(conf.percent_decay * 100),
            len(conf.users),
            conf.total_decayed,
        )
        if ignored_roles:
            joined = ", ".join(ignored_roles)
            txt += _("**Ignored Roles**\n") + joined
        embed = discord.Embed(
            title=_("BankDecay Settings"),
            description=txt,
            color=ctx.author.color,
        )
        await ctx.send(embed=embed)

    @bankdecay.command(name="toggle")
    async def toggle_decay(self, ctx: commands.Context):
        """
        Toggle the bank decay feature on or off.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.enabled = not conf.enabled
        await ctx.send(_("Bank decay has been {}.").format(_("enabled") if conf.enabled else _("disabled")))
        await self.save()

    @bankdecay.command(name="setdays")
    async def set_inactive_days(self, ctx: commands.Context, days: int):
        """
        Set the number of inactive days before decay starts.
        """
        if days < 0:
            await ctx.send(_("Inactive days cannot be negative."))
            return
        conf = self.db.get_conf(ctx.guild)
        conf.inactive_days = days
        await ctx.send(_("Inactive days set to {}.").format(days))
        await self.save()

    @bankdecay.command(name="setpercent")
    async def set_percent_decay(self, ctx: commands.Context, percent: float):
        """
        Set the percentage of decay that occurs after the inactive period.

        **Example**
        If decay is 5%, then after the set days of inactivity they will lose 5% of their balance every day.
        """
        if not 0 <= percent <= 1:
            await ctx.send(_("Percent decay must be between 0 and 1."))
            return
        conf = self.db.get_conf(ctx.guild)
        conf.percent_decay = percent
        await ctx.send(_("Percent decay set to {}%.").format(round(percent * 100)))
        await self.save()

    @bankdecay.command(name="resettotal")
    async def reset_total_decayed(self, ctx: commands.Context):
        """
        Reset the total amount decayed to zero.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.total_decayed = 0
        await ctx.send(_("Total decayed amount has been reset to 0."))
        await self.save()

    @bankdecay.command(name="decaynow")
    async def decay_now(self, ctx: commands.Context, confirm: bool):
        """
        Run a decay cycle on this server right now
        """
        if not confirm:
            txt = _("Not decaying user bank accounts")
            return await ctx.send(txt)
        conf = self.db.get_conf(ctx.guild)
        if not conf.enabled:
            txt = _("The decay system is currently disabled!")
            return await ctx.send(txt)
        async with ctx.typing():
            users_decayed, total_decayed = await self.decay_guild(ctx.guild)
        txt = _("- Users Affected: {}\n- Total Credits Decayed: {}").format(users_decayed, total_decayed)
        await ctx.send(txt)

    @bankdecay.command(name="initialize")
    async def initialize_guild(self, ctx: commands.Context):
        """
        Initialize the server and add every member to the config.
        """
        initialized = 0
        conf = self.db.get_conf(ctx.guild)
        for member in ctx.guild.members:
            if member.bot:  # Skip bots
                continue
            if member.id in conf.users:
                continue
            conf.get_user(member)  # This will add the member to the config if not already present
            initialized += 1
        grammar = _("member") if initialized == 1 else _("members")
        await ctx.send(_("Server initialized! {} added to the config.").format(f"{initialized} {grammar}"))
        await self.save()

    @bankdecay.command(name="seen")
    async def last_seen(self, ctx: commands.Context, *, user: discord.Member | int):
        """
        Check when a user was last active (if at all)
        """
        conf = self.db.get_conf(ctx.guild)
        uid = user if isinstance(user, int) else user.id
        if uid not in conf.users:
            txt = _("This user is not in the config yet!")
            return await ctx.send(txt)
        user: User = conf.get_user(uid)
        txt = _("User was last seen {}").format(f"{user.seen_f} ({user.seen_r})")
        await ctx.send(txt)

    @bankdecay.command(name="ignorerole")
    async def ignore_role(self, ctx: commands.Context, *, role: discord.Role):
        """
        Add/Remove a role from the ignore list

        Users with an ignored role will not have their balance decay
        """
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.ignored_roles:
            conf.ignored_roles.remove(role.id)
            txt = _("Role removed from the ignore list.")
        else:
            conf.ignored_roles.append(role.id)
            txt = _("Role added to the ignore list.")
        await ctx.send(txt)
        await self.save()
