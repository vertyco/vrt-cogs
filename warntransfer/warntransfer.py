import datetime

import discord
from redbot.core import commands, modlog

LOADING = "https://i.imgur.com/l3p6EMX.gif"


class WarnTransfer(commands.Cog):
    """Transfer WarnSystem data to core"""

    __author__ = "Vertyco#0117"
    __version__ = "0.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = (
            f"{helpcmd}\n"
            f"Cog Version: {self.__version__}\n"
            f"Author: {self.__author__}"
        )
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="warntransfer")
    @commands.is_owner()
    async def wtrans(self, ctx):
        """WarnSystem Transfer Options"""
        pass

    @wtrans.command(name="movetocore")
    async def modlog(self, ctx):
        """
        Import WarnSystem data to core modlog

        This command will import ALL WarnSystem cases to core modlog.

        **Please Note**
        Running this command again after the initial run will create duplicate cases, as it does not keep track of what
        cases have already been added.
        """
        warnsystem = self.bot.get_cog("WarnSystem")
        if not warnsystem:
            return await ctx.send(
                "WarnSystem is not loaded/installed. Please load it before importing"
            )
        embed = discord.Embed(
            description="Importing ModLog cases...", color=discord.Color.orange()
        )
        embed.set_thumbnail(url=LOADING)
        msg = await ctx.send(embed=embed)
        wsmodlogs = await warnsystem.data.custom("MODLOGS").all()
        async with ctx.typing():
            success, failed = await self.import_ws(ctx, msg, wsmodlogs)
            if success:
                res = f"Finished importing {success} cases!"
                if failed:
                    res += f"\nFailed to import {failed} cases!"
                embed = discord.Embed(description=res, color=discord.Color.green())
                await msg.edit(embed=embed)
            else:
                res = "No cases imported!"
                if failed:
                    res += f"\nFailed to import {failed} cases!"
                embed = discord.Embed(description=res, color=discord.Color.blue())
                await msg.edit(embed=embed)

    async def import_ws(self, ctx, msg: discord.Message, wsmodlogs: dict):
        count = 0
        failed = 0
        for guild_id, userdict in wsmodlogs.items():
            if not userdict:
                continue
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue

            # Disable the modlog channel to make things go faster and not spam the logs
            try:
                channel = await modlog.get_modlog_channel(guild)
            except RuntimeError:
                # Channel is already disabled or hasnt been set yet
                channel = None
                pass
            else:
                await modlog.set_modlog_channel(guild, None)

            for user_id, w in userdict.items():
                warns = w["x"]  # List of warns
                if not warns:
                    continue
                for warning in warns:  # Each warning is a dict
                    t = warning["level"]
                    if t == 2:
                        wtype = "smute"
                    elif t == 3:
                        wtype = "kick"
                    elif t == 4:
                        wtype = "softban"
                    elif t == 5:
                        wtype = "ban"
                    else:
                        wtype = "warning"
                    author = warning["author"]
                    reason = warning["reason"]
                    time = warning["time"]
                    time = datetime.datetime.fromtimestamp(time)

                    try:
                        await modlog.create_case(
                            self.bot,
                            guild,
                            time,
                            wtype,
                            int(user_id),
                            int(author),
                            reason,
                            until=None,
                            channel=None,
                        )
                        # log.info(f"ModLog {wtype} case created for {user_id}")
                        count += 1
                    except PermissionError:
                        await ctx.send(
                            f"Failed to create case for User: {user_id} in guild: {guild.name}"
                        )
                        failed += 1
                        continue

                    if count % 25 == 0:
                        embed = discord.Embed(
                            description="Importing ModLog cases...",
                            color=discord.Color.orange(),
                        )
                        embed.set_thumbnail(url=LOADING)
                        embed.set_footer(text=f"{count} imported so far")
                        await msg.edit(embed=embed)

            # Re-enable the modlog channel if it was disabled
            if channel:
                await modlog.set_modlog_channel(guild, channel)
        return count, failed
