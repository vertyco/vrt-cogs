import logging
import re
import typing as t

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common.dynamic_menu import DynamicMenu

PING_RE = re.compile(r"<@!?(\d+)>")
log = logging.getLogger("red.vrt.vrtutils.noping")


class NoPing(MixinMeta):
    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_guild=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def noping(self, ctx: commands.Context):
        """Toggle whether you want to be pinged"""
        is_admin = await self.bot.is_admin(ctx.author)
        automod_rule: t.List[discord.AutoModRule] = await ctx.guild.fetch_automod_rules()
        created = False
        for rule in automod_rule:
            if "no ping" in rule.name.lower():
                break
        else:
            # A rule will need to be created
            if not is_admin:
                return await ctx.send("An admin needs to use this command to establish the automod rule.")
            mod_roles = await self.bot.get_mod_roles(ctx.guild)
            admin_roles = await self.bot.get_admin_roles(ctx.guild)
            rule = await ctx.guild.create_automod_rule(
                name="No Ping",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(keyword_filter=[f"*<@{ctx.author.id}>*"]),
                actions=[
                    discord.AutoModRuleAction(
                        type=discord.AutoModRuleActionType.block_message,
                        custom_message="This user does not want to be pinged!",
                    ),
                ],
                exempt_roles=mod_roles + admin_roles,
                reason="No Ping rule for users who do not want to be pinged.",
            )
            created = True

        blocked_ids: list[str] = PING_RE.findall(", ".join(rule.trigger.keyword_filter))
        if len(blocked_ids) >= 1000:
            # Max limit reached
            pruned = await self.prune_noping_list(ctx.guild)
            if not pruned:
                return await ctx.send(
                    "The No Ping rule is at its limit (only 1000 users can be blacklisted from being pinged). 😢"
                )
            # Fetch the rule again and recompile
            automod_rule: discord.AutoModRule = await ctx.guild.fetch_automod_rule(rule.id)
            blocked_ids: list[str] = PING_RE.findall(", ".join(rule.trigger.keyword_filter))

        user_id = str(ctx.author.id)
        if created:
            txt = "You will no longer be pinged."
        elif user_id in blocked_ids:
            blocked_ids.remove(user_id)
            new_triggers = [f"*<@{user_id}>*" for user_id in blocked_ids]
            txt = "You can now be pinged."
        else:
            blocked_ids.append(user_id)
            new_triggers = [f"*<@{user_id}>*" for user_id in blocked_ids]
            txt = "You will no longer be pinged."

        if created:
            txt += " A new rule has been created for this, you may configure it further in the server settings."
        else:
            await rule.edit(trigger=discord.AutoModTrigger(keyword_filter=new_triggers), reason="User toggled No Ping.")
        await ctx.send(txt)

    @commands.group(name="nopingset")
    @commands.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def noping_group(self, ctx: commands.Context):
        """No Ping subcommands"""
        pass

    @noping_group.command(name="view", aliases=["list"])
    @commands.guild_only()
    async def noping_view(self, ctx: commands.Context):
        """List users who have opted out of being pinged"""
        automod_rule: t.List[discord.AutoModRule] = await ctx.guild.fetch_automod_rules()
        for rule in automod_rule:
            if "no ping" in rule.name.lower():
                break
        else:
            return await ctx.send("No No Ping rule found.")
        blocked_ids: list[str] = PING_RE.findall(", ".join(rule.trigger.keyword_filter))
        if not blocked_ids:
            return await ctx.send("No users have opted out of being pinged.")
        members = [f"{member.name} ({member.id})" for member in ctx.guild.members if str(member.id) in blocked_ids]
        members.sort(key=lambda x: x.lower())
        txt = "\n".join(members)
        color = await self.bot.get_embed_color(ctx)
        pages = [discord.Embed(description=page, color=color) for page in pagify(txt, page_length=800)]
        await DynamicMenu(ctx, pages).refresh()

    @noping_group.command(name="prune")
    @commands.guild_only()
    async def noping_prune(self, ctx: commands.Context):
        """Prune users no longer in the server from the No Ping rule"""
        pruned = await self.prune_noping_list(ctx.guild)
        if pruned is None:
            return await ctx.send("No No Ping rule found.")
        await ctx.send(f"Pruned {pruned} user(s) from the No Ping rule.")

    async def prune_noping_list(self, guild: discord.Guild) -> t.Union[int, None]:
        automod_rule: t.List[discord.AutoModRule] = await guild.fetch_automod_rules()
        for rule in automod_rule:
            if "no ping" in rule.name.lower():
                break
        else:
            return
        blocked_ids: list[str] = PING_RE.findall(", ".join(rule.trigger.keyword_filter))
        member_ids = [str(member.id) for member in guild.members]
        new_triggers = [f"*<@{user_id}>*" for user_id in blocked_ids if user_id in member_ids]
        if new_triggers != rule.trigger.keyword_filter:
            try:
                await rule.edit(trigger=discord.AutoModTrigger(keyword_filter=new_triggers), reason="Pruned users.")
            except discord.HTTPException:
                pass
        pruned = len(blocked_ids) - len(new_triggers)
        return pruned

    # Oh noo a listener in the commands section
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Check if bot has manage_guild permission
        if not member.guild.me:
            return
        if not member.guild.me.guild_permissions.manage_guild:
            return
        if await self.bot.cog_disabled_in_guild(self, member.guild):
            return
        # Remove the user from the no ping rule if they leave the server
        automod_rule: t.List[discord.AutoModRule] = await member.guild.fetch_automod_rules()
        for rule in automod_rule:
            if "no ping" in rule.name.lower():
                break
        else:
            return
        blocked_ids: list[str] = PING_RE.findall(", ".join(rule.trigger.keyword_filter))
        user_id = str(member.id)
        if user_id in blocked_ids:
            blocked_ids.remove(user_id)
            new_triggers = [f"*<@{user_id}>*" for user_id in blocked_ids]
            try:
                await rule.edit(
                    trigger=discord.AutoModTrigger(keyword_filter=new_triggers),
                    reason="User left the server.",
                )
            except discord.HTTPException:
                pass
