import asyncio
import typing as t
from io import BytesIO
from time import perf_counter

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    box,
    humanize_number,
    humanize_timedelta,
    pagify,
)

from ..abc import MixinMeta
from ..common import const, utils
from ..common.models import Emojis, Prestige

_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.group(name="levelset", aliases=["lvlset", "lset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def levelset(self, ctx: commands.Context):
        """Configure LevelUp Settings"""
        pass

    @levelset.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """View all LevelUP settings"""
        conf = self.db.get_conf(ctx.guild)
        txt = _(
            "**Main**\n"
            "`System Enabled:  `{}\n"
            "`Profile Type:    `{}\n"
            "`Style Override:  `{}\n"
            "`Include Balance: `{}\n"
            "**Messages**\n"
            "`Message XP:     `{}\n"
            "`Min Msg Length: `{}\n"
            "`Cooldown:       `{}\n"
            "`Command XP:     `{}\n"
            "**Voice**\n"
            "`Voice XP:         `{} per minute\n"
            "`Ignore Muted:     `{}\n"
            "`Ignore Solo:      `{}\n"
            "`Ignore Deafened:  `{}\n"
            "`Ignore Invisible: `{}\n"
            "**Level Algorithm**\n"
            "`Base Multiplier:  `{}\n"
            "`Exp Multiplier:   `{}\n"
            "`Equation:         `{}\n"
            "**LevelUps**\n"
            "`Notify In Channel: `{}\n"
            "• Send levelup message in the channel the user is typing in\n"
            "`Notify in DMs:     `{}\n"
            "• Send levelup message in DMs\n"
            "`Notify Channel:    `{}\n"
            "• Log channel for levelup messages\n"
            "`Mention User:      `{}\n"
            "• This will mention the user in the levelup message\n"
            "`AutoRemove Roles:  `{}\n"
            "• Remove the previous level role when a user levels up\n"
        ).format(
            _("Yes") if conf.enabled else _("NO!⚠️"),
            _("Embeds") if conf.use_embeds else _("Images"),
            str(conf.style_override).title(),
            _("Yes") if conf.showbal else _("No"),
            f"{conf.xp[0]} - {conf.xp[1]}",
            conf.min_length,
            utils.humanize_delta(conf.cooldown),
            conf.command_xp,
            humanize_number(conf.voicexp),
            conf.ignore_muted,
            conf.ignore_solo,
            conf.ignore_deafened,
            conf.ignore_invisible,
            conf.algorithm.base,
            conf.algorithm.exp,
            f"{conf.algorithm.base} x (level ^ {conf.algorithm.exp}) = XP",
            conf.notify,
            conf.notifydm,
            f"<#{conf.notifylog}>" if conf.notifylog else _("None"),
            conf.notifymention,
            conf.autoremove,
        )
        embed = discord.Embed(
            title=_("LevelUp Settings"),
            description=txt.strip(),
            color=await self.bot.get_embed_color(ctx),
        )
        if conf.levelroles:
            joined = "\n".join(
                _("• Level {}: {}").format(level, f"<@&{role_id}>") for level, role_id in conf.levelroles.items()
            )
            chunks = list(pagify(joined, page_length=1024))
            if len(chunks) == 1:
                embed.add_field(name=_("Level Roles"), value=joined, inline=False)
            else:
                for i, chunk in enumerate(chunks):
                    embed.add_field(
                        name=_("Level Roles") if i == 0 else _("Level Roles Continued"), value=chunk, inline=False
                    )
        if conf.prestigelevel and conf.prestigedata:
            roles = _("➣ Prestige roles will {}").format(
                _("**Stack**") if conf.stackprestigeroles else _("**Not Stack**")
            )
            req = _("➣ Requires reaching level {} to activate").format(conf.prestigelevel)
            if conf.keep_level_roles:
                req += _("\n➣ Level roles will be kept after prestiging")
            else:
                req += _("\n➣ Level roles will be reset after prestiging")
            joined = "\n".join(
                _("• Prestige {}: {}").format(level, f"<@&{prestige.role}>")
                for level, prestige in conf.prestigedata.items()
            )
            embed.add_field(name=_("Prestige"), value=f"{roles}\n{req}\n{joined}", inline=False)
        if conf.rolebonus.voice:
            joined = "\n".join(
                _("• {}: `{}`").format(f"<@&{role_id}>", xp_range) for role_id, xp_range in conf.rolebonus.voice.items()
            )
            embed.add_field(name=_("Voice XP Bonus Roles"), value=joined, inline=False)
        if conf.channelbonus.voice:
            joined = "\n".join(
                _("• {}: `{}`").format(f"<#{channel_id}>", xp_range)
                for channel_id, xp_range in conf.channelbonus.voice.items()
            )
            embed.add_field(name=_("Voice XP Bonus Channels"), value=joined, inline=False)
        if conf.streambonus:
            embed.add_field(
                name=_("Stream Bonus"),
                value=_("Bonus for streaming: {}").format(f"`{conf.streambonus}`"),
                inline=False,
            )
        if conf.rolebonus.msg:
            joined = "\n".join(
                _("• {}: `{}`").format(f"<@&{role_id}>", xp_range) for role_id, xp_range in conf.rolebonus.msg.items()
            )
            embed.add_field(name=_("Message XP Bonus Roles"), value=joined, inline=False)
        if conf.channelbonus.msg:
            joined = "\n".join(
                _("• {}: `{}`").format(f"<#{channel_id}>", xp_range)
                for channel_id, xp_range in conf.channelbonus.msg.items()
            )
            embed.add_field(name=_("Message XP Bonus Channels"), value=joined, inline=False)
        if conf.allowedroles:
            joined = ", ".join([f"<@&{role_id}>" for role_id in conf.allowedroles if ctx.guild.get_role(role_id)])
            embed.add_field(name=_("Allowed Roles"), value=joined, inline=False)
        if conf.allowedchannels:
            joined = ", ".join(
                [f"<#{channel_id}>" for channel_id in conf.allowedchannels if ctx.guild.get_channel(channel_id)]
            )
            embed.add_field(name=_("Allowed Channels"), value=joined, inline=False)
        if conf.ignoredroles:
            joined = ", ".join([f"<@&{role_id}>" for role_id in conf.ignoredroles if ctx.guild.get_role(role_id)])
            embed.add_field(name=_("Ignored Roles"), value=joined, inline=False)
        if conf.ignoredchannels:
            joined = ", ".join(
                [f"<#{channel_id}>" for channel_id in conf.ignoredchannels if ctx.guild.get_channel(channel_id)]
            )
            embed.add_field(name=_("Ignored Channels"), value=joined, inline=False)
        if conf.ignoredusers:
            joined = ", ".join([f"<@{user_id}>" for user_id in conf.ignoredusers if ctx.guild.get_member(user_id)])
            embed.add_field(name=_("Ignored Users"), value=joined, inline=False)
        if dm_role := conf.role_awarded_dm:
            embed.add_field(name=_("LevelUp DM Role Message"), value=dm_role, inline=False)
        if dm_msg := conf.levelup_dm:
            embed.add_field(name=_("LevelUp DM Message"), value=dm_msg, inline=False)
        if msg := conf.levelup_msg:
            embed.add_field(name=_("LevelUp Message"), value=msg, inline=False)
        if msg_role := conf.role_awarded_msg:
            embed.add_field(name=_("LevelUp Role Message"), value=msg_role, inline=False)
        if roles := conf.role_groups:
            joined = ", ".join([f"<@&{role_id}>" for role_id in roles if ctx.guild.get_role(role_id)])
            txt = _("The following roles gain exp as a group:\n{}").format(joined)
            embed.add_field(name=_("Role Exp Groups"), value=txt, inline=False)
        if ctx.author.id not in self.bot.owner_ids:
            txt = _("➣ Profile Cache Time\n")
            if self.db.cache_seconds:
                txt += _("Profiles will be cached for {}\n").format(utils.humanize_delta(self.db.cache_seconds))
            else:
                txt += _("Profiles are not cached\n")
            txt += _("➣ Profile Rendering\n")
            if self.db.render_gifs:
                txt += _("Users with animated profiles will render as a GIF")
            else:
                txt += _("Profiles will always be static images")
            embed.add_field(
                name=_("Bot Owner Settings"),
                value=txt,
                inline=False,
            )
        await ctx.send(embed=embed)

    @levelset.command(name="forcestyle")
    async def force_profile_style(self, ctx: commands.Context, style: t.Literal["default", "runescape", "none"]):
        """
        Force a profile style for all users

        Specify `none` to disable the forced style
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.use_embeds:
            return await ctx.send(
                _("LevelUp is using embeds, use the {} command to toggle between embed and image profiles.").format(
                    f"`{ctx.clean_prefix}levelset embeds`"
                )
            )
        if style == "none":
            conf.style_override = None
            self.save()
            return await ctx.send(_("Style override has been **disabled**!"))
        conf.style_override = style
        self.save()
        await ctx.send(_("Style override has been set to **{}**").format(style))

    @levelset.command(name="toggle")
    async def toggle_levelup(self, ctx: commands.Context):
        """Toggle the LevelUp system"""
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.enabled else _("**Enabled**")
        conf.enabled = not conf.enabled
        self.save()
        await ctx.send(_("LevelUp has been {}").format(status))

    @levelset.command(name="rolegroup")
    async def add_remove_role_group(self, ctx: commands.Context, role: t.Union[discord.Role, int]):
        """
        Add or remove a role to the role group

        These roles gain their own experience points as a group
        When a member gains xp while having this role, the xp they earn is also added to the role group
        """
        conf = self.db.get_conf(ctx.guild)
        role_id = role if isinstance(role, int) else role.id
        if role_id in conf.role_groups:
            del conf.role_groups[role_id]
            txt = _("The role {} will no longer gain experience points.").format(f"<@&{role_id}>")
        else:
            if not ctx.guild.get_role(role_id):
                return await ctx.send(_("Role not found!"))
            conf.role_groups[role_id] = 0
            txt = _("The role {} will now gain expecience points from all members that have it.").format(
                f"<@&{role_id}>"
            )
        self.save()
        await ctx.send(txt)

    @levelset.command(name="addxp")
    async def add_xp_to_user(
        self,
        ctx: commands.Context,
        user_or_role: t.Union[discord.Member, discord.Role],
        xp: int,
    ):
        """Add XP to a user or role"""
        conf = self.db.get_conf(ctx.guild)
        if isinstance(user_or_role, discord.Member):
            profile = conf.get_profile(user_or_role)
            profile.xp += xp
            txt = _("Added {} XP to {}").format(xp, user_or_role.name)
            self.save()
            return await ctx.send(txt)
        for user in user_or_role.members:
            profile = conf.get_profile(user)
            profile.xp += xp
        txt = _("Added {} XP {} member(s) with the {} role").format(
            xp,
            len(user_or_role.members),
            user_or_role.mention,
        )
        await ctx.send(txt)
        self.save()

    @levelset.command(name="removexp")
    async def remove_xp_from_user(
        self,
        ctx: commands.Context,
        user_or_role: t.Union[discord.Member, discord.Role],
        xp: int,
    ):
        """Remove XP from a user or role"""
        conf = self.db.get_conf(ctx.guild)
        if isinstance(user_or_role, discord.Member):
            profile = conf.get_profile(user_or_role)
            profile.xp -= min(profile.xp, xp)
            txt = _("Removed {} XP from {}").format(min(profile.xp, xp), user_or_role.name)
            self.save()
            return await ctx.send(txt)
        for user in user_or_role.members:
            profile = conf.get_profile(user)
            profile.xp -= min(profile.xp, xp)
        txt = _("Removed {} XP from {} member(s) with the {} role").format(
            xp,
            len(user_or_role.members),
            user_or_role.mention,
        )
        await ctx.send(txt)
        self.save()

    @levelset.command(name="algorithm", aliases=["algo"])
    async def set_level_algorithm(
        self,
        ctx: commands.Context,
        part: t.Literal["base", "exp"],
        value: t.Union[float, int],
    ):
        """
        Customize the leveling algorithm for your server
        • Default base is 100
        • Default exp is 2

        **Equation**
        ➣ Getting required XP for a level
        • `base * (level ^ exp) = XP`
        ➣ Getting required level for an XP value
        • `level = (XP / base) ^ (1 / exp)`

        **Arguments**
        ➣ `part` - The part of the algorithm to change
        ➣ `value` - The value to set it to
        """
        if part == "exp":
            value = float(value)
            if value <= 0:
                return await ctx.send(_("Exponent must be greater than 0"))
            if value > 10:
                return await ctx.send(_("Exponent must be less than 10"))
        else:
            value = round(value)
            if value < 0:
                return await ctx.send(_("Base must be greater than 0"))
        conf = self.db.get_conf(ctx.guild)
        setattr(conf.algorithm, part, value)
        self.save()
        await ctx.send(_("Algorithm {} has been set to {}").format(part, value))

    @levelset.command(name="commandxp")
    async def set_command_xp(self, ctx: commands.Context):
        """Toggle whether users can gain Exp from running commands"""
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.command_xp else _("**Enabled**")
        conf.command_xp = not conf.command_xp
        self.save()
        await ctx.send(_("Command XP has been {}").format(status))

    @levelset.command(name="dm")
    async def toggle_dm(self, ctx: commands.Context):
        """
        Toggle DM notifications

        Determines whether LevelUp messages are DM'd to the user
        """
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.notifydm else _("**Enabled**")
        conf.notifydm = not conf.notifydm
        self.save()
        await ctx.send(_("DM notifications have been {}").format(status))

    @levelset.command(name="resetemojis")
    async def reset_emojis(self, ctx: commands.Context):
        """Reset the emojis to default"""
        conf = self.db.get_conf(ctx.guild)
        conf.emojis = Emojis()
        self.save()
        await ctx.send(_("Emojis have been reset to default"))

    @levelset.command(name="emojis")
    @commands.bot_has_permissions(embed_links=True)
    async def set_emojis(
        self,
        ctx: commands.Context,
        level: t.Union[discord.Emoji, discord.PartialEmoji, str],
        prestige: t.Union[discord.Emoji, discord.PartialEmoji, str],
        star: t.Union[discord.Emoji, discord.PartialEmoji, str],
        chat: t.Union[discord.Emoji, discord.PartialEmoji, str],
        voicetime: t.Union[discord.Emoji, discord.PartialEmoji, str],
        experience: t.Union[discord.Emoji, discord.PartialEmoji, str],
        balance: t.Union[discord.Emoji, discord.PartialEmoji, str],
    ):
        """Set the emojis used to represent each stat type"""

        async def test_reactions(
            ctx: commands.Context,
            emojis: t.List[t.Union[discord.Emoji, discord.PartialEmoji, str]],
        ) -> bool:
            try:
                [await ctx.message.add_reaction(e) for e in emojis]
                return True
            except Exception as e:
                await ctx.send(f"Cannot add reactions: {e}")
                return False

        reactions = [level, prestige, star, chat, voicetime, experience, balance]
        if not await test_reactions(ctx, reactions):
            return

        def get_emoji_value(emoji: t.Union[discord.Emoji, discord.PartialEmoji, str]):
            if isinstance(emoji, str):
                return emoji
            if emoji.id:
                return emoji.id
            return str(emoji)

        conf = self.db.get_conf(ctx.guild)
        conf.emojis.level = get_emoji_value(level)
        conf.emojis.trophy = get_emoji_value(prestige)
        conf.emojis.star = get_emoji_value(star)
        conf.emojis.chat = get_emoji_value(chat)
        conf.emojis.mic = get_emoji_value(voicetime)
        conf.emojis.bulb = get_emoji_value(experience)
        conf.emojis.money = get_emoji_value(balance)
        self.save()
        await ctx.send(_("Emojis have been set"))

    @levelset.command(name="embeds")
    async def toggle_embeds(self, ctx: commands.Context):
        """Toggle using embeds or generated pics"""
        conf = self.db.get_conf(ctx.guild)
        if self.db.force_embeds:
            txt = _("Profile rendering is locked to Embeds only by the bot owner!")
            conf.use_embeds = False
            self.save()
            return await ctx.send(txt)
        status = _("**Images**") if conf.use_embeds else _("**Embeds**")
        conf.use_embeds = not conf.use_embeds
        self.save()
        await ctx.send(_("Profile rendering has been set to {}").format(status))

    @levelset.command(name="levelchannel")
    async def set_level_channel(
        self,
        ctx: commands.Context,
        channel: t.Union[discord.TextChannel, None] = None,
    ):
        """
        Set LevelUp log channel

        Set a channel for all level up messages to send to.

        If level notify is off and mention is on, the bot will mention the user in the channel
        """
        conf = self.db.get_conf(ctx.guild)
        if not channel and not conf.notifylog:
            return await ctx.send_help()
        if not channel and conf.notifylog:
            conf.notifylog = 0
            self.save()
            return await ctx.send(_("LevelUp messages will no longer be sent to a specific channel"))
        conf.notifylog = channel.id
        self.save()
        await ctx.send(_("LevelUp messages will now be sent to {}").format(channel.mention))

    @levelset.command(name="levelnotify")
    async def toggle_levelup_notifications(self, ctx: commands.Context):
        """
        Send levelup message in the channel the user is typing in

        Send a message in the channel a user is typing in when they level up
        """
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.notify else _("**Enabled**")
        conf.notify = not conf.notify
        self.save()
        await ctx.send(_("LevelUp notifications have been {}").format(status))

    @levelset.command(name="mention")
    async def toggle_mention(self, ctx: commands.Context):
        """
        Toggle whether to mention the user in the level up message

        If level notify is on AND a log channel is set, the user will only be mentioned in the channel they are in.
        """
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.notifymention else _("**Enabled**")
        conf.notifymention = not conf.notifymention
        self.save()
        await ctx.send(_("Mentioning user in LevelUp messages has been {}").format(status))

    @levelset.command(name="seelevels")
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def see_levels(self, ctx: commands.Context):
        """
        Test the level algorithm
        View the first 20 levels using the current algorithm to test experience curve
        """
        async with ctx.typing():
            conf = self.db.get_conf(ctx.guild)
            txt, filebytes = await asyncio.to_thread(
                utils.plot_levels,
                base=conf.algorithm.base,
                exponent=conf.algorithm.exp,
                cooldown=conf.cooldown,
                xp_range=conf.xp,
            )
            file = discord.File(BytesIO(filebytes), filename="levels.png")
            img = "attachment://levels.png"
            example = _(
                "XP required for a level = Base * Level^ᵉˣᵖ\n\n"
                "Approx time is the time it would take for a user to reach a level with randomized breaks"
            )
            desc = _("`Base Multiplier:  `") + f"{conf.algorithm.base}\n"
            desc += _("`Exp Multiplier:   `") + f"{conf.algorithm.exp}\n"
            desc += _("`Experience Range: `") + f"{conf.xp}\n"
            desc += _("`Message Cooldown: `") + f"{conf.cooldown}\n"
            desc += f"{box(example)}\n{box(txt, lang='python')}"
            embed = discord.Embed(
                title=_("Leveling Algorithm"),
                description=desc,
                color=await self.bot.get_embed_color(ctx),
            )
            embed.set_image(url=img)
            await ctx.send(file=file, embed=embed)

    @levelset.command(name="setlevel")
    async def set_level(self, ctx: commands.Context, user: discord.Member, level: int):
        """
        Set a user's level

        **Arguments**
        • `user` - The user to set the level for
        • `level` - The level to set the user to
        """
        async with ctx.typing():
            conf = self.db.get_conf(ctx.guild)
            profile = conf.get_profile(user)
            profile.level = level
            profile.xp = conf.algorithm.get_xp(level)
            self.save()
            reason = _("{} set {}'s level to {}").format(ctx.author.name, user.name, level)
            added, removed = await self.ensure_roles(user, conf, reason)
            if added or removed:
                txt = _("{}'s level has been set to {} and their roles have been updated").format(user.name, level)
            else:
                txt = _("{}'s level has been set to {}").format(user.name, level)
            await ctx.send(txt)

    @levelset.command(name="setprestige")
    async def set_user_prestige(self, ctx: commands.Context, user: discord.Member, prestige: int):
        """
        Set a user to a specific prestige level

        Prestige roles will need to be manually added/removed when using this command
        """
        conf = self.db.get_conf(ctx.guild)
        if user.id not in conf.users:
            return await ctx.send(_("User has not been registered yet!"))
        if not conf.prestigedata:
            return await ctx.send(_("Prestige levels have not been set!"))
        if prestige and prestige not in conf.prestigedata:
            return await ctx.send(_("That prestige level does not exist!"))
        profile = conf.get_profile(user)
        profile.prestige = prestige
        self.save()
        await ctx.send(_("{} has been set to prestige level {}").format(user.name, prestige))

    @levelset.command(name="showbalance", aliases=["showbal"])
    async def toggle_profile_balance(self, ctx: commands.Context):
        """Toggle whether to show user's economy credit balance in their profile"""
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.showbal else _("**Enabled**")
        conf.showbal = not conf.showbal
        self.save()
        await ctx.send(_("Including economy balance in profiles has been {}").format(status))

    @levelset.command(name="starcooldown")
    async def set_star_cooldown(self, ctx: commands.Context, seconds: int):
        """
        Set the star cooldown

        Users can give another user a star every X seconds
        """
        conf = self.db.get_conf(ctx.guild)
        conf.starcooldown = seconds
        self.save()
        await ctx.send(_("Star cooldown has been set to {} seconds").format(seconds))

    @levelset.command(name="starmention")
    async def toggle_star_mention(self, ctx: commands.Context):
        """
        Toggle star reaction mentions
        Toggle whether the bot mentions that a user reacted to a message with a star
        """
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.starmention else _("**Enabled**")
        conf.starmention = not conf.starmention
        self.save()
        await ctx.send(_("Mentioning user when they receive a star has been {}").format(status))

    @levelset.command(name="starmentiondelete")
    async def toggle_starmention_autodelete(self, ctx: commands.Context, deleted_after: int):
        """
        Toggle whether the bot auto-deletes the star mentions
        Set to 0 to disable auto-delete
        """
        conf = self.db.get_conf(ctx.guild)
        conf.starmentionautodelete = deleted_after
        if deleted_after:
            await ctx.send(_("Star mentions will be deleted after {} seconds").format(deleted_after))
        else:
            await ctx.send(_("Star mentions will not be auto-deleted"))
        self.save()

    @levelset.group(name="allowed")
    async def allowed(self, ctx: commands.Context):
        """Base command for all allowed lists"""
        pass

    @allowed.command(name="channel")
    async def allowed_channel(
        self,
        ctx: commands.Context,
        *,
        channel: t.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.ForumChannel],
    ):
        """
        Add/Remove a channel in the allowed list
        If the allow list is not empty, only channels in the list will gain XP

        Use the command with a channel already in the allowed list to remove it
        """
        conf = self.db.get_conf(ctx.guild)
        if channel.id in conf.allowedchannels:
            conf.allowedchannels.remove(channel.id)
            txt = _("Channel {} has been removed from the allowed list").format(channel.mention)
        else:
            conf.allowedchannels.append(channel.id)
            txt = _("Channel {} has been added to the allowed list").format(channel.mention)
        self.save()
        await ctx.send(txt)

    @allowed.command(name="role")
    async def allowed_role(
        self,
        ctx: commands.Context,
        *,
        role: discord.Role,
    ):
        """
        Add/Remove a role in the allowed list
        If the allow list is not empty, only roles in the list will gain XP

        Use the command with a role already in the allowed list to remove it
        """
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.allowedroles:
            conf.allowedroles.remove(role.id)
            txt = _("Role {} has been removed from the allowed list").format(role.mention)
        else:
            conf.allowedroles.append(role.id)
            txt = _("Role {} has been added to the allowed list").format(role.mention)
        self.save()
        await ctx.send(txt)

    @levelset.group(name="ignore")
    async def ignore(self, ctx: commands.Context):
        """Base command for all ignore lists"""
        pass

    @ignore.command(name="channel")
    async def ignore_channel(
        self,
        ctx: commands.Context,
        *,
        channel: t.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.ForumChannel],
    ):
        """
        Add/Remove a channel in the ignore list
        Channels in the ignore list don't gain XP

        Use the command with a channel already in the ignore list to remove it
        """
        conf = self.db.get_conf(ctx.guild)
        if channel.id in conf.ignoredchannels:
            conf.ignoredchannels.remove(channel.id)
            txt = _("Channel {} has been removed from the ignore list").format(channel.mention)
        else:
            conf.ignoredchannels.append(channel.id)
            txt = _("Channel {} has been added to the ignore list").format(channel.mention)
        self.save()
        await ctx.send(txt)

    @ignore.command(name="role")
    async def ignore_role(
        self,
        ctx: commands.Context,
        *,
        role: discord.Role,
    ):
        """
        Add/Remove a role in the ignore list
        Members with roles in the ignore list don't gain XP

        Use the command with a role already in the ignore list to remove it
        """
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.ignoredroles:
            conf.ignoredroles.remove(role.id)
            txt = _("Role {} has been removed from the ignore list").format(role.mention)
        else:
            conf.ignoredroles.append(role.id)
            txt = _("Role {} has been added to the ignore list").format(role.mention)
        self.save()
        await ctx.send(txt)

    @ignore.command(name="user")
    async def ignore_user(
        self,
        ctx: commands.Context,
        *,
        user: discord.Member,
    ):
        """
        Add/Remove a user in the ignore list
        Members in the ignore list don't gain XP

        Use the command with a user already in the ignore list to remove them
        """
        conf = self.db.get_conf(ctx.guild)
        if user.id in conf.ignoredusers:
            conf.ignoredusers.remove(user.id)
            txt = _("User {} has been removed from the ignore list").format(user.name)
        else:
            conf.ignoredusers.append(user.id)
            txt = _("User {} has been added to the ignore list").format(user.name)
        self.save()
        await ctx.send(txt)

    @levelset.group(name="levelupmessages", aliases=["lvlalerts", "levelalerts", "lvlmessages", "lvlmsg"])
    async def set_levelup_alerts(self, ctx: commands.Context):
        """Level up alert messages

        **Arguments**
        The following placeholders can be used:
        • `{username}`: The user's name
        • `{mention}`: Mentions the user
        • `{displayname}`: The user's display name
        • `{level}`: The level the user just reached
        • `{server}`: The server the user is in

        **If using dmrole or msgrole**
        • `{role}`: The role the user just recieved
        """

    @set_levelup_alerts.command(name="view")
    async def view_levelup_alerts(self, ctx: commands.Context):
        """View the current level up alert messages"""
        conf = self.db.get_conf(ctx.guild)
        color = await self.bot.get_embed_color(ctx)
        desc = _("Current LevelUp Alert Messages\n-# None means the default will be used")
        embed = discord.Embed(description=desc, color=color)
        value = _("-# When a user levels up\n{}").format(str(conf.levelup_dm or None))
        embed.add_field(name=_("LevelUp DM"), value=value, inline=False)
        value = _("-# When a user levels up and receives a role\n{}").format(str(conf.role_awarded_dm or None))
        embed.add_field(name=_("LevelUp DM Role"), value=value, inline=False)
        value = _("-# When a user levels up\n{}").format(str(conf.levelup_msg or None))
        embed.add_field(name=_("LevelUp Message"), value=value, inline=False)
        value = _("-# When a user levels up and receives a role\n{}").format(str(conf.role_awarded_msg or None))
        embed.add_field(name=_("LevelUp Role Message"), value=value, inline=False)
        await ctx.send(embed=embed)

    @set_levelup_alerts.command(name="dm")
    async def set_levelup_dm(self, ctx: commands.Context, *, message: str = None):
        """
        Set the DM a user gets when they level up (Without recieving a role).

        **Arguments**
        The following placeholders can be used:
        • `{username}`: The user's name
        • `{mention}`: Mentions the user
        • `{displayname}`: The user's display name
        • `{level}`: The level the user just reached
        • `{server}`: The server the user is in
        """
        conf = self.db.get_conf(ctx.guild)
        if not message and not conf.levelup_dm:
            return await ctx.send_help()
        if not message and conf.levelup_dm:
            conf.levelup_dm = None
            self.save()
            return await ctx.send(_("LevelUp DM message has been removed"))
        kwargs = {
            "username": ctx.author.name,
            "mention": ctx.author.mention,
            "displayname": ctx.author.display_name,
            "level": 1,
            "server": ctx.guild.name,
        }
        try:
            msg = message.format(**kwargs)
        except KeyError as e:
            return await ctx.send(_("Invalid placeholder used: {}").format(e))
        conf.levelup_dm = message
        self.save()
        embed = discord.Embed(description=msg, color=await self.bot.get_embed_color(ctx))
        await ctx.send(_("LevelUp DM message has been set"), embed=embed)

    @set_levelup_alerts.command(name="dmrole")
    async def set_levelup_dmrole(self, ctx: commands.Context, *, message: str = None):
        """
        Set the DM a user gets when they level up and recieve a role.

        **Arguments**
        The following placeholders can be used:
        • `{username}`: The user's name
        • `{mention}`: Mentions the user
        • `{displayname}`: The user's display name
        • `{level}`: The level the user just reached
        • `{server}`: The server the user is in
        • `{role}`: The role the user just recieved
        """
        conf = self.db.get_conf(ctx.guild)
        if not message and not conf.role_awarded_dm:
            return await ctx.send_help()
        if not message and conf.role_awarded_dm:
            conf.role_awarded_dm = None
            self.save()
            return await ctx.send(_("LevelUp DM role message has been removed"))
        kwargs = {
            "username": ctx.author.name,
            "mention": ctx.author.mention,
            "displayname": ctx.author.display_name,
            "level": 1,
            "server": ctx.guild.name,
            "role": "Example Role",
        }
        try:
            msg = message.format(**kwargs)
        except KeyError as e:
            return await ctx.send(_("Invalid placeholder used: {}").format(e))
        conf.role_awarded_dm = message
        self.save()
        embed = discord.Embed(description=msg, color=await self.bot.get_embed_color(ctx))
        await ctx.send(_("LevelUp DM role message has been set"), embed=embed)

    @set_levelup_alerts.command(name="msg")
    async def set_levelup_msg(self, ctx: commands.Context, *, message: str = None):
        """
        Set the message sent when a user levels up.

        **Arguments**
        The following placeholders can be used:
        • `{username}`: The user's name
        • `{mention}`: Mentions the user
        • `{displayname}`: The user's display name
        • `{level}`: The level the user just reached
        • `{server}`: The server the user is in
        """
        conf = self.db.get_conf(ctx.guild)
        if not message and not conf.levelup_msg:
            return await ctx.send_help()
        if not message and conf.levelup_msg:
            conf.levelup_msg = ""
            self.save()
            return await ctx.send(_("LevelUp message has been removed"))
        kwargs = {
            "username": ctx.author.name,
            "mention": ctx.author.mention,
            "displayname": ctx.author.display_name,
            "level": 1,
            "server": ctx.guild.name,
        }
        try:
            msg = message.format(**kwargs)
        except KeyError as e:
            return await ctx.send(_("Invalid placeholder used: {}").format(e))
        conf.levelup_msg = message
        self.save()
        embed = discord.Embed(description=msg, color=await self.bot.get_embed_color(ctx))
        await ctx.send(_("LevelUp message has been set"), embed=embed)

    @set_levelup_alerts.command(name="msgrole")
    async def set_levelup_msgrole(self, ctx: commands.Context, *, message: str = None):
        """
        Set the message sent when a user levels up and recieves a role.

        **Arguments**
        The following placeholders can be used:
        • `{username}`: The user's name
        • `{mention}`: Mentions the user
        • `{displayname}`: The user's display name
        • `{level}`: The level the user just reached
        • `{server}`: The server the user is in
        • `{role}`: The role the user just recieved
        """
        conf = self.db.get_conf(ctx.guild)
        if not message and not conf.role_awarded_msg:
            return await ctx.send_help()
        if not message and conf.role_awarded_msg:
            conf.role_awarded_msg = ""
            self.save()
            return await ctx.send(_("LevelUp role message has been removed"))
        kwargs = {
            "username": ctx.author.name,
            "mention": ctx.author.mention,
            "displayname": ctx.author.display_name,
            "level": 1,
            "server": ctx.guild.name,
            "role": "Example Role",
        }
        try:
            msg = message.format(**kwargs)
        except KeyError as e:
            return await ctx.send(_("Invalid placeholder used: {}").format(e))
        conf.role_awarded_msg = message
        self.save()
        embed = discord.Embed(description=msg, color=await self.bot.get_embed_color(ctx))
        await ctx.send(_("LevelUp role message has been set"), embed=embed)

    @levelset.group(name="messages", aliases=["message", "msg"])
    async def message_group(self, ctx: commands.Context):
        """Message settings"""

    @message_group.command(name="channelbonus")
    async def msg_chan_bonus(
        self,
        ctx: commands.Context,
        channel: t.Union[discord.TextChannel, discord.CategoryChannel],
        min_xp: commands.positive_int,
        max_xp: commands.positive_int,
    ):
        """
        Add a range of bonus XP to apply to certain channels

        This bonus applies to message xp

        Set both min and max to 0 to remove the role bonus
        """
        if min_xp > max_xp:
            return await ctx.send(_("Min XP value cannot be greater than Max XP value"))
        conf = self.db.get_conf(ctx.guild)
        if channel.id in conf.channelbonus.msg:
            if min_xp == 0 and max_xp == 0:
                del conf.channelbonus.msg[channel.id]
                self.save()
                return await ctx.send(_("Channel bonus has been removed"))
            conf.channelbonus.msg[channel.id] = [min_xp, max_xp]
            self.save()
            return await ctx.send(_("Channel bonus has been updated"))

        if min_xp == 0 and max_xp == 0:
            return await ctx.send(_("XP range cannot be 0"))
        conf.channelbonus.msg[channel.id] = [min_xp, max_xp]
        self.save()
        await ctx.send(_("Channel bonus has been set"))

    @message_group.command(name="cooldown")
    async def set_cooldown(self, ctx: commands.Context, cooldown: commands.positive_int):
        """
        Cooldown threshold for message XP

        When a user sends a message they will have to wait X seconds before their message
        counts as XP gained
        """
        conf = self.db.get_conf(ctx.guild)
        conf.cooldown = cooldown
        self.save()
        await ctx.send(_("Cooldown has been set to {} seconds").format(cooldown))

    @message_group.command(name="length")
    async def set_length(self, ctx: commands.Context, length: commands.positive_int):
        """
        Set minimum message length for XP
        Minimum length a message must be to count towards XP gained

        Set to 0 to disable
        """
        conf = self.db.get_conf(ctx.guild)
        conf.min_length = length
        self.save()
        await ctx.send(_("Minimum message length has been set to {}").format(length))

    @message_group.command(name="rolebonus")
    async def msg_role_bonus(
        self,
        ctx: commands.Context,
        role: discord.Role,
        min_xp: commands.positive_int,
        max_xp: commands.positive_int,
    ):
        """
        Add a range of bonus XP to apply to certain roles

        This bonus applies to message xp

        Set both min and max to 0 to remove the role bonus
        """
        conf = self.db.get_conf(ctx.guild)
        if min_xp > max_xp:
            return await ctx.send(_("Min XP value cannot be greater than Max XP value"))
        if role.id in conf.rolebonus.msg:
            if min_xp == 0 and max_xp == 0:
                del conf.rolebonus.msg[role.id]
                self.save()
                return await ctx.send(_("Role bonus has been removed"))
            conf.rolebonus.msg[role.id] = [min_xp, max_xp]
            self.save()
            return await ctx.send(_("Role bonus has been updated"))
        conf.rolebonus.msg[role.id] = [min_xp, max_xp]
        self.save()
        await ctx.send(_("Role bonus has been set"))

    @message_group.command(name="xp")
    async def set_xp(self, ctx: commands.Context, min_xp: commands.positive_int, max_xp: commands.positive_int):
        """
        Set message XP range

        Set the Min and Max amount of XP that a message can gain
        Default is 3 min and 6 max
        """
        conf = self.db.get_conf(ctx.guild)
        if min_xp > max_xp:
            return await ctx.send(_("Min XP value cannot be greater than Max XP value"))
        if min_xp == 0 and max_xp == 0:
            return await ctx.send(_("XP range cannot be 0"))
        conf.xp = [min_xp, max_xp]
        self.save()
        await ctx.send(_("Message XP range has been set to {} - {}").format(min_xp, max_xp))

    @levelset.group(name="roles")
    async def level_roles(self, ctx: commands.Context):
        """Level role assignment"""

    @level_roles.command(name="autoremove")
    async def toggle_autoremove(self, ctx: commands.Context):
        """Automatic removal of previous level roles"""
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.autoremove else _("**Enabled**")
        conf.autoremove = not conf.autoremove
        self.save()
        await ctx.send(_("Automatic removal of previous level roles has been {}").format(status))

    @level_roles.command(name="add")
    async def add_level_role(self, ctx: commands.Context, level: int, role: discord.Role):
        """Assign a role to a level"""
        conf = self.db.get_conf(ctx.guild)
        if role >= ctx.guild.me.top_role:
            return await ctx.send(_("I cannot assign roles higher than my top role!"))
        if role >= ctx.author.top_role:
            return await ctx.send(_("You cannot assign roles higher than your top role!"))
        if level in conf.levelroles:
            txt = _("The role associated with level {} has been updated").format(level)
        else:
            txt = _("The role associated with level {} has been added").format(level)
        conf.levelroles[level] = role.id
        self.save()
        await ctx.send(txt)

    @level_roles.command(name="remove", aliases=["rem", "del"])
    async def del_level_role(self, ctx: commands.Context, level: int):
        """Unassign a role from a level"""
        conf = self.db.get_conf(ctx.guild)
        if level not in conf.levelroles:
            return await ctx.send(_("There is no role associated with level {}").format(level))
        del conf.levelroles[level]
        self.save()
        await ctx.send(_("The role associated with level {} has been removed").format(level))

    @level_roles.command(name="initialize", aliases=["init"])
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    @commands.cooldown(1, 240, commands.BucketType.guild)
    async def init_roles(self, ctx: commands.Context):
        """
        Initialize level roles

        This command is for if you added level roles after users have achieved that level,
        it will apply all necessary roles to a user according to their level and prestige
        """
        start = perf_counter()
        roles_added = 0
        roles_removed = 0
        embed = discord.Embed(
            description=_("Synchronizing level roles, this may take a while..."),
            color=discord.Color.magenta(),
        )
        embed.set_thumbnail(url=const.LOADING)
        msg = await ctx.send(embed=embed)
        last_update = perf_counter()
        conf = self.db.get_conf(ctx.guild)
        reason = _("Level role initialization")
        member_count = len(ctx.guild.members)
        async with ctx.typing():
            for idx, user in enumerate(ctx.guild.members):
                added, removed = await self.ensure_roles(user, conf, reason)
                roles_added += len(added)
                roles_removed += len(removed)

                # Update message every 5% of the way if there are more than 40 users
                if member_count > 40 and idx % (member_count // 20) == 0 and perf_counter() - last_update > 5:
                    desc = _("Synchronizing level roles, this may take a while...\n{:.0%} complete").format(
                        idx / member_count
                    )
                    embed.description = desc
                    asyncio.create_task(msg.edit(embed=embed))
                    last_update = perf_counter()

        if not roles_added and not roles_removed:
            return await msg.edit(
                content=_("No roles were added or removed"),
                embed=None,
            )
        desc = _("Role initialization complete\nRoles added: {}\nRoles removed: {}").format(roles_added, roles_removed)
        embed = discord.Embed(description=desc, color=discord.Color.green())
        td = round(perf_counter() - start)
        delta = humanize_timedelta(seconds=td)
        foot = _("Initialization took {} to complete.").format(delta)
        embed.set_footer(text=foot)
        await msg.edit(embed=embed)

    @levelset.group(name="voice")
    async def voice_group(self, ctx: commands.Context):
        """Voice settings"""

    @voice_group.command(name="channelbonus")
    async def voice_chan_bonus(
        self,
        ctx: commands.Context,
        channel: discord.VoiceChannel,
        min_xp: commands.positive_int,
        max_xp: commands.positive_int,
    ):
        """
        Add a range of bonus XP to apply to certain channels

        This bonus applies to voice time xp per minute.
        Example: 2 minutes in a channel with a 1-2 bonus will give 2-4 XP

        Set both min and max to 0 to remove the channel bonus.
        """
        conf = self.db.get_conf(ctx.guild)
        if min_xp > max_xp:
            return await ctx.send(_("Min XP value cannot be greater than Max XP value"))
        if channel.id in conf.channelbonus.voice:
            if min_xp == 0 and max_xp == 0:
                del conf.channelbonus.voice[channel.id]
                self.save()
                return await ctx.send(_("Channel bonus has been removed"))
            conf.channelbonus.voice[channel.id] = [min_xp, max_xp]
            self.save()
            return await ctx.send(_("Channel bonus has been updated"))
        if min_xp == 0 and max_xp == 0:
            return await ctx.send(_("XP range cannot be 0"))
        conf.channelbonus.voice[channel.id] = [min_xp, max_xp]
        self.save()
        await ctx.send(_("Channel bonus has been set"))

    @voice_group.command(name="streambonus")
    async def voice_stream_bonus(
        self, ctx: commands.Context, min_xp: commands.positive_int, max_xp: commands.positive_int
    ):
        """
        Add a range of bonus XP to users who are Discord streaming

        This bonus applies to voice time xp

        Set both min and max to 0 to remove the bonus
        """
        conf = self.db.get_conf(ctx.guild)
        if min_xp > max_xp:
            return await ctx.send(_("Min XP value cannot be greater than Max XP value"))
        if min_xp == 0 and max_xp == 0:
            conf.streambonus = None
            self.save()
            return await ctx.send(_("Stream bonus has been removed"))
        conf.streambonus = [min_xp, max_xp]
        self.save()
        await ctx.send(_("Stream bonus has been set"))

    @voice_group.command(name="rolebonus")
    async def voice_role_bonus(
        self,
        ctx: commands.Context,
        role: discord.Role,
        min_xp: commands.positive_int,
        max_xp: commands.positive_int,
    ):
        """
        Add a range of bonus XP to apply to certain roles

        This bonus applies to voice time xp

        Set both min and max to 0 to remove the role bonus
        """
        conf = self.db.get_conf(ctx.guild)
        if min_xp > max_xp:
            return await ctx.send(_("Min XP value cannot be greater than Max XP value"))
        if role.id in conf.rolebonus.voice:
            if min_xp == 0 and max_xp == 0:
                del conf.rolebonus.voice[role.id]
                self.save()
                return await ctx.send(_("Role bonus has been removed"))
            conf.rolebonus.voice[role.id] = [min_xp, max_xp]
            self.save()
            return await ctx.send(_("Role bonus has been updated"))
        if min_xp == 0 and max_xp == 0:
            return await ctx.send(_("XP range cannot be 0"))
        conf.rolebonus.voice[role.id] = [min_xp, max_xp]
        self.save()
        await ctx.send(_("Role bonus has been set"))

    @voice_group.command(name="deafened")
    async def ignore_deafened(self, ctx: commands.Context):
        """
        Ignore deafened voice users
        Toggle whether deafened users in a voice channel can gain voice XP
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.ignore_deafened:
            txt = _("Deafened users can now gain XP while in a voice channel")
            conf.ignore_deafened = False
        else:
            txt = _("Deafened users will no longer gain XP while in a voice channel")
            conf.ignore_deafened = True
        self.save()
        await ctx.send(txt)

    @voice_group.command(name="invisible")
    async def ignore_invisible(self, ctx: commands.Context):
        """
        Ignore invisible voice users
        Toggle whether invisible users in a voice channel can gain voice XP
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.ignore_invisible:
            txt = _("Invisible users can now gain XP while in a voice channel")
            conf.ignore_invisible = False
        else:
            txt = _("Invisible users will no longer gain XP while in a voice channel")
            conf.ignore_invisible = True
        self.save()
        await ctx.send(txt)

    @voice_group.command(name="muted")
    async def ignore_muted(self, ctx: commands.Context):
        """
        Ignore muted voice users
        Toggle whether self-muted users in a voice channel can gain voice XP
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.ignore_muted:
            txt = _("Muted users can now gain XP while in a voice channel")
            conf.ignore_muted = False
        else:
            txt = _("Muted users will no longer gain XP while in a voice channel")
            conf.ignore_muted = True
        self.save()
        await ctx.send(txt)

    @voice_group.command(name="solo")
    async def ignore_solo(self, ctx: commands.Context):
        """
        Ignore solo voice users
        Toggle whether solo users in a voice channel can gain voice XP
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.ignore_solo:
            txt = _("Solo users can now gain XP while in a voice channel")
            conf.ignore_solo = False
        else:
            txt = _("Solo users will no longer gain XP while in a voice channel")
            conf.ignore_solo = True
        self.save()
        await ctx.send(txt)

    @voice_group.command(name="xp")
    async def set_voice_xp(self, ctx: commands.Context, voice_xp: commands.positive_int):
        """
        Set voice XP gain
        Sets the amount of XP gained per minute in a voice channel (default is 2)
        """
        conf = self.db.get_conf(ctx.guild)
        conf.voicexp = voice_xp
        self.save()
        await ctx.send(_("Voice XP has been set to {} per minute").format(voice_xp))

    @levelset.group(name="prestige")
    async def prestige_group(self, ctx: commands.Context):
        """Prestige settings"""

    @prestige_group.command(name="keeproles")
    async def toggle_keep_roles(self, ctx: commands.Context):
        """Keep level roles after prestiging"""
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.keep_level_roles else _("**Enabled**")
        conf.keep_level_roles = not conf.keep_level_roles
        self.save()
        await ctx.send(_("Keeping roles after prestiging has been {}").format(status))

    @prestige_group.command(name="level")
    async def prestige_level(self, ctx: commands.Context, level: commands.positive_int):
        """
        Set the level required to prestige
        """
        conf = self.db.get_conf(ctx.guild)
        conf.prestigelevel = level
        self.save()
        await ctx.send(_("Prestige level has been set to {}").format(level))

    @prestige_group.command(name="stack")
    async def toggle_stack_roles(self, ctx: commands.Context):
        """
        Toggle stacking roles on prestige

        For example each time you prestige, you keep the previous prestige roles
        """
        conf = self.db.get_conf(ctx.guild)
        status = _("**Disabled**") if conf.stackprestigeroles else _("**Enabled**")
        conf.stackprestigeroles = not conf.stackprestigeroles
        self.save()
        await ctx.send(_("Stacking roles on prestige has been {}").format(status))

    @prestige_group.command(name="add")
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def add_prestige_level(
        self,
        ctx: commands.Context,
        prestige: int,
        role: discord.Role,
        emoji: t.Union[discord.Emoji, discord.PartialEmoji, str],
    ):
        """
        Add a role to a prestige level
        """
        conf = self.db.get_conf(ctx.guild)
        if role >= ctx.guild.me.top_role:
            return await ctx.send(_("I cannot assign roles higher than my top role!"))
        if role >= ctx.author.top_role:
            return await ctx.send(_("You cannot assign roles higher than your top role!"))
        if prestige in conf.prestigedata:
            return await ctx.send(_("This prestige level has already been set!"))
        url = utils.get_twemoji(emoji) if isinstance(emoji, str) else emoji.url
        prestige_obj = Prestige(
            role=role.id,
            emoji_string=str(emoji),
            emoji_url=url,
        )
        conf.prestigedata[prestige] = prestige_obj
        self.save()
        await ctx.send(_("Role and emoji have been set for prestige level {}").format(prestige))

    @prestige_group.command(name="remove", aliases=["rem", "del"])
    async def remove_prestige_level(self, ctx: commands.Context, prestige: int):
        """
        Remove a prestige level
        """
        conf = self.db.get_conf(ctx.guild)
        if prestige not in conf.prestigedata:
            return await ctx.send(_("That prestige level does not exist!"))
        del conf.prestigedata[prestige]
        self.save()
        await ctx.send(_("Prestige level {} has been removed").format(prestige))
