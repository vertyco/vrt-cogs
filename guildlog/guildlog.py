import logging

import discord
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import box

log = logging.getLogger("red.vrt.guildlog")


class GuildLog(commands.Cog):
    """
    Log when the bot joins or leaves a guild
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.1.3"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        default_guild = {
            "channel": None,
            "embeds": False,
            "join": {"msg": "default", "color": 56865},
            "leave": {"msg": "default", "color": 15158332},
        }
        self.config.register_guild(**default_guild)

    @commands.Cog.listener()
    async def on_guild_join(self, new_guild: discord.Guild):
        conf = await self.config.all_guilds()
        if not conf:
            return
        for guild_id, data in conf.items():
            if not data:
                continue
            if not data["channel"]:
                continue
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            channel: discord.TextChannel = guild.get_channel(int(data["channel"]))
            if not channel:
                continue
            perms = channel.permissions_for(guild.me).send_messages
            if not perms:
                log.warning(f"Lacking permissions to send to join log in {guild.name}")
                continue
            embeds = data["embeds"]
            msg = data["join"]["msg"]
            if msg == "default":
                msg = f"✅ Joined guild **{new_guild.name}!** That makes {len(self.bot.guilds)} servers now!"
            else:
                bots = 0
                users = 0
                for m in new_guild.members:
                    if m.bot:
                        bots += 1
                    else:
                        users += 1
                params = {
                    "guild": new_guild.name,
                    "guildid": new_guild.id,
                    "servers": len(self.bot.guilds),
                    "botname": self.bot.user.name,
                    "bots": bots,
                    "members": users,
                }
                msg = msg.format(**params)
            if embeds and channel.permissions_for(channel.guild.me).embed_links:
                color = data["join"].get("color", 56865)
                embed = discord.Embed(description=msg, color=color)
                await channel.send(embed=embed)
            else:
                await channel.send(msg)

    @commands.Cog.listener()
    async def on_guild_remove(self, old_guild: discord.Guild):
        conf = await self.config.all_guilds()
        if not conf:
            return
        for guild_id, data in conf.items():
            if not data:
                continue
            if not data["channel"]:
                continue
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            channel = guild.get_channel(int(data["channel"]))
            if not channel:
                continue
            perms = channel.permissions_for(guild.me).send_messages
            if not perms:
                log.warning(f"Lacking permissions to send to join log in {guild.name}")
                continue
            embeds = data["embeds"]
            msg = data["leave"]["msg"]
            if msg == "default":
                msg = f"❌ Left guild **{old_guild.name}!** That makes {len(self.bot.guilds)} servers now!"
            else:
                bots = 0
                users = 0
                for m in old_guild.members:
                    if m.bot:
                        bots += 1
                    else:
                        users += 1
                params = {
                    "guild": old_guild.name,
                    "guildid": old_guild.id,
                    "servers": len(self.bot.guilds),
                    "botname": self.bot.user.name,
                    "bots": bots,
                    "members": users,
                }
                msg = msg.format(**params)
            if embeds:
                color = data["leave"].get("color", 15158332)
                embed = discord.Embed(description=msg, color=color)
                await channel.send(embed=embed)
            else:
                await channel.send(msg)

    @commands.group(name="guildlogset", aliases=["glset"])
    @commands.guild_only()
    @commands.is_owner()
    async def gset(self, ctx):
        """Configure GuildLog Settings"""
        pass

    @gset.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx):
        """View GuildLog Settings"""
        conf = await self.config.guild(ctx.guild).all()
        cid = conf["channel"]
        if cid:
            channel = ctx.guild.get_channel(int(cid))
            if channel:
                channel = channel.mention
            else:
                channel = cid
        else:
            channel = "Not Set"

        msg = f"`Log Channel: `{channel}\n" f"`Use Embeds:  `{conf['embeds']}"
        embed = discord.Embed(title="Guild Log Settings", description=msg)
        jcolor = conf["join"]["color"]
        jmsg = conf["join"]["msg"]
        embed.add_field(name=f"Join Msg (color: {jcolor})", value=box(jmsg), inline=False)
        lcolor = conf["leave"]["color"]
        lmsg = conf["leave"]["msg"]
        embed.add_field(name=f"Leave Msg (color: {lcolor})", value=box(lmsg), inline=False)
        await ctx.send(embed=embed)

    @gset.command(name="channel")
    async def set_log_channel(self, ctx, *, channel: discord.TextChannel = None):
        """Set a channel for the bot to log guilds it leaves/joins"""
        if channel:
            await self.config.guild(ctx.guild).channel.set(str(channel.id))
            await ctx.send(f"Log channel set to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).channel.set(None)
            await ctx.send("Log channel **Disabled**")

    @gset.command(name="embeds")
    async def toggle_embeds(self, ctx):
        """(Toggle) Embeds for join/leave log"""
        toggle = await self.config.guild(ctx.guild).embeds()
        if toggle:
            await self.config.guild(ctx.guild).embeds.set(False)
            await ctx.send("Embeds have been **Disabled**")
        else:
            await self.config.guild(ctx.guild).embeds.set(True)
            await ctx.send("Embeds have been **Enabled**")

    @gset.group(name="join")
    async def jset(self, ctx):
        """Configure join settings"""
        pass

    @jset.command(name="msg")
    async def join_msg(self, ctx, *, message: str):
        """
        Set the guild join message

        Valid placeholders are:
        `{guild}` - the name of the guild the bot just joined
        `{guildid}` - the id of the guild the bot just joined
        `{servers}` - the amount of servers the bot is now in
        `{botname}` - the name of the bot
        `{bots}` - the amount of bots in the guild
        `{members}` - the member count of the guild

        To set back to default just to `default` as the message value
        """
        await self.config.guild(ctx.guild).join.msg.set(message)
        await ctx.tick()

    @jset.command(name="color")
    @commands.bot_has_permissions(embed_links=True)
    async def join_color(self, ctx, color: int):
        """
        Set the color of the guild join embed

        If embeds are on, this will be the join color.
        Color value must be an integer
        """
        try:
            embed = discord.Embed(description="Your join messages will now use this color", color=color)
            await ctx.send(embed=embed)
        except Exception as e:
            return await ctx.send(f"Failed to set embed color:\n{box(str(e))}")
        await self.config.guild(ctx.guild).join.color.set(color)
        await ctx.tick()

    @gset.group(name="leave")
    async def lset(self, ctx):
        """Configure leave settings"""
        pass

    @lset.command(name="msg")
    async def leave_msg(self, ctx, *, message: str):
        """
        Set the guild leave message

        Valid placeholders are:
        `{guild}` - the name of the guild the bot just joined
        `{guildid}` - the id of the guild the bot just joined
        `{servers}` - the amount of servers the bot is now in
        `{botname}` - the name of the bot
        `{bots}` - the amount of bots that were in the guild
        `{members}` - the member count of the guild

        To set back to default just to `default` as the message value
        """
        await self.config.guild(ctx.guild).leave.msg.set(message)
        await ctx.tick()

    @lset.command(name="color")
    @commands.bot_has_permissions(embed_links=True)
    async def leave_color(self, ctx, color: int):
        """
        Set the color of the guild leave embed

        If embeds are on, this will be the leave color.
        Color value must be an integer
        """
        try:
            embed = discord.Embed(description="Your leave messages will now use this color", color=color)
            await ctx.send(embed=embed)
        except Exception as e:
            return await ctx.send(f"Failed to set embed color:\n{box(str(e))}")
        await self.config.guild(ctx.guild).join.color.set(color)
        await ctx.tick()
