import asyncio
import inspect
import random
import typing as t

import discord
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common.dpymenu import DEFAULT_CONTROLS, menu
from ..common.utils import teredo_unobfuscate


class Misc(MixinMeta):
    @commands.hybrid_command(name="throwerror")
    @commands.is_owner()
    async def throw_error(self, ctx: commands.Context):
        """
        Throw an unhandled exception

        A zero division error will be raised
        """
        bad = 10 / 0
        await ctx.send(f"Woah how'd you get here? {bad}")

    @commands.command(name="getsource")
    @commands.is_owner()
    async def get_sourcecode(self, ctx: commands.Context, *, command: str):
        """
        Get the source code of a command
        """
        command = self.bot.get_command(command)
        if command is None:
            return await ctx.send("Command not found!")
        try:
            source_code = inspect.getsource(command.callback)
            if comments := inspect.getcomments(command.callback):
                source_code = comments + "\n" + source_code
        except OSError:
            return await ctx.send("Failed to pull source code")
        pagified = [p for p in pagify(source_code, escape_mass_mentions=True, page_length=1900)]
        pages = []
        for index, p in enumerate(pagified):
            pages.append(box(p, lang="python") + f"\nPage {index + 1}/{len(pagified)}")
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="text2binary")
    async def text2binary(self, ctx: commands.Context, *, text: str):
        """Convert text to binary"""
        # binary_string = ''.join(format(ord(c), 'b') for c in text)
        try:
            binary_string = "".join(format(ord(i), "08b") for i in text)
            for p in pagify(binary_string):
                await ctx.send(p)
        except ValueError:
            await ctx.send("I could not convert that text to binary :(")

    @commands.command(name="binary2text")
    async def binary2text(self, ctx: commands.Context, *, binary_string: str):
        """Convert a binary string to text"""
        binary_string = binary_string.replace(" ", "").replace("\n", "")
        try:
            text = "".join(chr(int(binary_string[i * 8 : i * 8 + 8], 2)) for i in range(len(binary_string) // 8))
            await ctx.send(text)
        except ValueError:
            await ctx.send("I could not convert that binary string to text :(")

    @commands.command(name="randomnum", aliases=["rnum"])
    async def random_number(self, ctx: commands.Context, minimum: int = 1, maximum: int = 100):
        """Generate a random number between the numbers specified"""
        if minimum >= maximum:
            return await ctx.send("Minimum needs to be lower than maximum!")
        num = random.randint(minimum, maximum)
        await ctx.send(f"Result: `{num}`")

    @commands.command(name="reactmsg")
    @commands.mod_or_permissions(add_reactions=True)
    @commands.bot_has_guild_permissions(add_reactions=True)
    async def add_a_reaction(
        self,
        ctx: commands.Context,
        emoji: t.Union[discord.Emoji, discord.PartialEmoji, str],
        message: discord.Message = None,
    ):
        """
        Add a reaction to a message
        """
        if not message and hasattr(ctx.message, "reference") and hasattr(ctx.message.reference, "resolved"):
            message = ctx.message.reference.resolved
        if not message or not isinstance(message, discord.Message):
            message = ctx.message

        if not message.channel.permissions_for(ctx.me).add_reactions:
            return await ctx.send("I don't have permissions to react in that channel!")
        if not message.channel.permissions_for(ctx.author).add_reactions:
            return await ctx.send("You don't have permissions to react in that channel!")
        await message.add_reaction(emoji)

    @commands.command(name="cleanadventurealerts")
    @commands.admin_or_permissions(administrator=True)
    async def clear_adventure_alerts(self, ctx: commands.Context):
        """Prune adventure alerts from members no longer in the server

        This command requires the AdventureAlert cog by TrustyJAID to be loaded.
        https://github.com/TrustyJAID/Trusty-cogs/tree/master
        """
        cog = self.bot.get_cog("AdventureAlert")
        if cog is None:
            txt = "The [AdventureAlert](https://github.com/TrustyJAID/Trusty-cogs/tree/master) cog is not loaded."
            return await ctx.send(txt)

        async with ctx.typing():
            conf: Config = cog.config
            settings = await conf.guild(ctx.guild).all()

            keys = [
                "users",
                "adventure_users",
                "cart_users",
                "miniboss_users",
                "ascended_users",
                "transcended_users",
                "immortal_users",
                "possessed_users",
            ]
            member_ids = []
            for key in keys:
                member_ids.extend(settings.get(key, []))

            ids_to_remove = set()
            for member_id in set(member_ids):
                if not ctx.guild.get_member(member_id):
                    ids_to_remove.add(member_id)
            jobs = []
            for member_id in ids_to_remove:
                func = cog.red_delete_data_for_user(requester="user", user_id=member_id)
                jobs.append(func)
            await asyncio.gather(*jobs)
            await ctx.send(f"Removed {len(ids_to_remove)} members from the adventure alerts.")

    @commands.command(name="teredo")
    async def teredo(self, ctx: commands.Context, *, ipv6: str):
        """Unobfuscate a Teredo IPv6 address"""
        try:
            result = teredo_unobfuscate(ipv6)
            txt = f"- Server IPv4: `{result['server_ipv4']}`\n"
            txt += f"- UDP Port: `{result['udp_port']}`\n"
            txt += f"- Client IPv4: `{result['client_ipv4']}`"
            await ctx.send(txt)
        except Exception as e:
            await ctx.send(f"Error: {e}")
