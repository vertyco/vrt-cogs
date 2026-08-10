import logging
from io import StringIO

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common.utils import build_pattern

log = logging.getLogger("red.vrt.swearjar")

# Discord embed field values cap at 1024 characters; reserve room for the trailing "and N more" note.
EMBED_FIELD_LIMIT = 1024


def join_mentions(mentions: list[str]) -> str:
    """Join mentions with a comma, truncating to stay under the embed field limit."""
    if not mentions:
        return "None"
    joined = ", ".join(mentions)
    if len(joined) <= EMBED_FIELD_LIMIT:
        return joined
    kept = []
    length = 0
    for index, mention in enumerate(mentions):
        addition = len(mention) if index == 0 else len(mention) + 2
        if length + addition > EMBED_FIELD_LIMIT - 30:
            break
        kept.append(mention)
        length += addition
    remaining = len(mentions) - len(kept)
    return f"{', '.join(kept)}, ... and {remaining} more"


class Admin(MixinMeta):
    @commands.group(name="swearjarset", aliases=["sjset"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def swearjarset(self, ctx: commands.Context):
        """Configure the swear jar."""
        pass

    @swearjarset.command(name="toggle")
    async def toggle_enabled(self, ctx: commands.Context):
        """Enable or disable the swear jar."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not enabled)
        status = "disabled" if enabled else "enabled"
        await ctx.send(f"Swear jar {status}.")

    @swearjarset.command(name="addword")
    async def add_word(self, ctx: commands.Context, word: str, boundary: bool = True, fine: int = None):
        """Add or update a swear word.

        **boundary**: `true` (default) matches whole words only, `false` matches inside other words.
        **fine**: credits charged for this word; leave empty to use the server default.

        Boundary comes first so you can set it without also naming a fine:
        `[p]swearjarset addword damn false`

        Wrap a multi-word entry in quotes so it is not parsed as extra arguments, for example:
        `[p]swearjarset addword "son of a bitch" true 25`
        """
        if fine is not None and fine < 0:
            await ctx.send("Fine cannot be negative.")
            return
        word = word.casefold().strip()
        if not word:
            await ctx.send("That word is empty.")
            return
        if build_pattern(word, boundary) is None:
            await ctx.send("That word has no letters or numbers for me to match on.")
            return
        async with self.config.guild(ctx.guild).words() as words:
            updating = word in words
            words[word] = {"fine": fine, "boundary": boundary}
        action = "Updated" if updating else "Added"
        await ctx.send(f"{action} word. Use `{ctx.clean_prefix}swearjarset words` to review the list.")
        await ctx.tick()

    @swearjarset.command(name="delword")
    async def del_word(self, ctx: commands.Context, word: str):
        """Remove a swear word."""
        word = word.casefold().strip()
        async with self.config.guild(ctx.guild).words() as words:
            if word not in words:
                await ctx.send("That word is not in the list.")
                return
            del words[word]
        await ctx.tick()

    @swearjarset.command(name="words")
    async def list_words(self, ctx: commands.Context):
        """DM you the configured swear words."""
        conf = await self.config.guild(ctx.guild).all()
        if not conf["words"]:
            await ctx.send("No words configured.")
            return
        buffer = StringIO()
        buffer.write(f"Swear words for {ctx.guild.name} (default fine: {conf['default_fine']})\n")
        for word, settings in sorted(conf["words"].items()):
            fine = settings.get("fine")
            fine_txt = str(fine) if fine is not None else f"default ({conf['default_fine']})"
            match_txt = "whole word" if settings.get("boundary", True) else "substring"
            buffer.write(f"- {word}: fine {fine_txt}, {match_txt}\n")
        try:
            await ctx.author.send(buffer.getvalue())
            await ctx.send("Sent you a DM with the word list.")
        except discord.HTTPException as e:
            log.warning("Failed to DM swear word list to %s", ctx.author.id, exc_info=e)
            await ctx.send("I could not DM you. Enable DMs from this server and try again.")

    @swearjarset.command(name="fine")
    async def set_default_fine(self, ctx: commands.Context, amount: int):
        """Set the default fine for words without their own fine."""
        if amount < 0:
            await ctx.send("Fine cannot be negative.")
            return
        await self.config.guild(ctx.guild).default_fine.set(amount)
        await ctx.send(f"Default fine set to {humanize_number(amount)}.")

    @swearjarset.command(name="respond")
    async def toggle_respond(self, ctx: commands.Context):
        """Toggle the in-channel message when someone is fined."""
        respond = await self.config.guild(ctx.guild).respond()
        await self.config.guild(ctx.guild).respond.set(not respond)
        status = "no longer" if respond else "now"
        await ctx.send(f"I will {status} respond in-channel when fining someone.")

    @swearjarset.command(name="ignorechannel")
    async def ignore_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Add or remove a channel from the ignore list."""
        async with self.config.guild(ctx.guild).ignored_channels() as channels:
            if channel.id in channels:
                channels.remove(channel.id)
                await ctx.send(f"{channel.mention} is no longer ignored.")
            else:
                channels.append(channel.id)
                await ctx.send(f"{channel.mention} is now ignored.")

    @swearjarset.command(name="ignorerole")
    async def ignore_role(self, ctx: commands.Context, role: discord.Role):
        """Add or remove a role from the ignore list."""
        async with self.config.guild(ctx.guild).ignored_roles() as roles:
            if role.id in roles:
                roles.remove(role.id)
                await ctx.send(f"`{role.name}` is no longer ignored.")
            else:
                roles.append(role.id)
                await ctx.send(f"`{role.name}` is now ignored.")

    @swearjarset.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View swear jar settings."""
        conf = await self.config.guild(ctx.guild).all()
        channels = [f"<#{cid}>" for cid in conf["ignored_channels"]]
        roles = [f"<@&{rid}>" for rid in conf["ignored_roles"]]
        embed = discord.Embed(title="Swear Jar Settings", color=ctx.author.color)
        embed.add_field(name="Enabled", value=str(conf["enabled"]))
        embed.add_field(name="Words configured", value=str(len(conf["words"])))
        embed.add_field(name="Default fine", value=humanize_number(conf["default_fine"]))
        embed.add_field(name="Respond in channel", value=str(conf["respond"]))
        embed.add_field(name="Jar total", value=humanize_number(conf["jar_total"]))
        embed.add_field(name="Ignored channels", value=join_mentions(channels))
        embed.add_field(name="Ignored roles", value=join_mentions(roles))
        await ctx.send(embed=embed)

    @swearjarset.command(name="reset")
    async def reset_jar(self, ctx: commands.Context, confirm: bool = False):
        """Reset the jar total and all member payment stats.

        Run with `True` to confirm: `[p]swearjarset reset true`
        """
        if not confirm:
            await ctx.send(
                f"This wipes the jar total and leaderboard. Run `{ctx.clean_prefix}swearjarset reset true` to confirm."
            )
            return
        await self.config.guild(ctx.guild).jar_total.set(0)
        await self.config.clear_all_members(ctx.guild)
        await ctx.send("Swear jar stats reset.")
