import logging
import typing as t
from io import StringIO

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify

log = logging.getLogger("red.vrt.commandlock")


class CogCommandConverter(t.NamedTuple):
    cog_or_command: commands.Command | commands.Cog
    is_cog: bool

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> "CogCommandConverter":
        if cog := ctx.bot.get_cog(argument):
            return cls(cog, True)
        if command := ctx.bot.get_command(argument):
            return cls(command, False)
        raise commands.BadArgument(f"Cog or command '{argument}' not found.")


class CommandLock(commands.Cog):
    """
    Lock command or cog usage to specific channels and redirect users to the correct ones.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 350053505815281665, force_registration=True)
        guild_config = {
            "cog_locks": {},  # {cog_name: [channel_ids]}
            "command_locks": {},  # {qualified_command_name: [channel_ids]}
            "whitelisted_roles": [],  # list[role_ids] that bypass all locks
        }
        self.config.register_guild(**guild_config)

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        # Requester can be "discord_deleted_user", "owner", "user", or "user_strict"
        return

    async def red_get_data_for_user(self, *, requester: str, user_id: int):
        # Requester can be "discord_deleted_user", "owner", "user", or "user_strict"
        return

    async def cog_load(self) -> None:
        self.bot.before_invoke(self.before_invoke_hook)

    async def cog_unload(self) -> None:
        self.bot.remove_before_invoke_hook(self.before_invoke_hook)

    async def before_invoke_hook(self, ctx: commands.Context):
        if await self.is_immune(ctx):
            return True
        allowed_channels = await self.get_allowed_channels(ctx)
        if not allowed_channels:
            # The allowed channels are channels they cannot access
            err = "There are no channels in which you have permission to use this command."
            await ctx.send(err, delete_after=30)
            raise commands.CheckFailure(err)
        channel = ctx.channel.parent if isinstance(ctx.channel, discord.Thread) else ctx.channel
        if channel in allowed_channels:
            return True
        mentions = []
        for channel in allowed_channels:
            if isinstance(channel, discord.CategoryChannel):
                for inner_channel in channel.channels:
                    mentions.append(inner_channel.mention)
            else:
                mentions.append(channel.mention)
        mentions = ", ".join(mentions)
        msg = f"{ctx.author.mention}, you can only use this command in the following channels: {mentions}"
        for p in pagify(msg, page_length=1900, delims=[",", "\n"]):
            await ctx.send(p, delete_after=30)
        raise commands.CheckFailure("Command used in disallowed channel.")

    async def is_immune(self, ctx: commands.Context) -> bool:
        if (
            isinstance(ctx.command, commands.commands._AlwaysAvailableCommand)
            or ctx.guild is None
            or ctx.guild.owner_id == ctx.author.id
            or await self.bot.is_owner(ctx.author)
            or not isinstance(ctx.author, discord.Member)
            or await self.bot.is_admin(ctx.author)
        ):
            log.debug("User %s is immune to command locks.", ctx.author)
            return True
        # Whitelisted roles bypass all locks
        whitelist = await self.config.guild(ctx.guild).whitelisted_roles()
        if whitelist and any(role.id in whitelist for role in ctx.author.roles):
            log.debug("User %s has a whitelisted role and is immune to command locks.", ctx.author)
            return True
        return False

    async def get_allowed_channels(
        self,
        ctx: commands.Context,
    ) -> set[discord.abc.GuildChannel]:
        command = ctx.command
        assert command.cog_name is not None, "Command has no cog_name in allowed_channels"
        allowed_channels: set[discord.abc.GuildChannel] = set()
        command_name = command.qualified_name
        cog_name = command.cog_name
        log.debug(f"Checking locks for command '{command_name}' in cog '{cog_name}'")
        conf = await self.config.guild(ctx.guild).all()
        if command_name in conf["command_locks"]:
            channel_ids = conf["command_locks"][command_name]
            for channel_id in channel_ids:
                channel = ctx.guild.get_channel_or_thread(channel_id)
                if channel:
                    allowed_channels.add(channel)
                    if isinstance(channel, discord.CategoryChannel):
                        for inner_channel in channel.channels:
                            allowed_channels.add(inner_channel)
        elif cog_name in conf["cog_locks"]:
            channel_ids = conf["cog_locks"][cog_name]
            for channel_id in channel_ids:
                channel = ctx.guild.get_channel_or_thread(channel_id)
                if channel:
                    allowed_channels.add(channel)
                    if isinstance(channel, discord.CategoryChannel):
                        for inner_channel in channel.channels:
                            allowed_channels.add(inner_channel)
        else:
            # No locks set, allow all channels
            allowed_channels = set(ctx.guild.channels).union(set(ctx.guild.threads))
        return set(
            c
            for c in allowed_channels
            if c.permissions_for(ctx.author).view_channel and c.permissions_for(ctx.author).send_messages
        )

    @commands.group(name="commandlock", aliases=["cmdlock"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def commandlock(self, ctx: commands.Context):
        """Manage command and cog locks to specific channels."""
        pass

    @commandlock.command(name="whitelistrole")
    async def whitelist_role(self, ctx: commands.Context, role: discord.Role):
        """Add/Remove whitelisted roles to bypass all command and cog locks."""
        whitelist = await self.config.guild(ctx.guild).whitelisted_roles()
        if role.id in whitelist:
            whitelist.remove(role.id)
            await self.config.guild(ctx.guild).whitelisted_roles.set(whitelist)
            await ctx.send(f"Role {role.mention} has been removed from the whitelist.")
        else:
            whitelist.append(role.id)
            await self.config.guild(ctx.guild).whitelisted_roles.set(whitelist)
            await ctx.send(f"Role {role.mention} has been added to the whitelist.")

    @commandlock.command(name="lock", aliases=["set", "add"])
    async def add_lock(
        self,
        ctx: commands.Context,
        allowed_channels: commands.Greedy[discord.abc.GuildChannel],
        *,
        cog_or_command: CogCommandConverter,
    ):
        """Add a lock to a cog or command to restrict its usage to the specified channels.

        **Notes:**
        - Bot owners, server owners, and admins are immune to command locks.
        - Whitelisted roles bypass all command and cog locks.
        - Command locks take precedence over cog locks.
        - Channels can be categories, in which case all channels within that category are included.

        **Examples:**
        `[p]commandlock lock #allowed-channel MyCog`
        `[p]commandlock lock channel_id channel_id_2 MyCommand`
        `[p]commandlock lock #channel1 #channel2 MyCog`
        """
        if not allowed_channels:
            await ctx.send("You must specify at least one channel to lock to.")
            return

        conf = await self.config.guild(ctx.guild).all()
        channel_ids = [channel.id for channel in allowed_channels]

        if cog_or_command.is_cog:
            cog: commands.Cog = cog_or_command.cog_or_command
            cog_name: str = cog.qualified_name
            conf["cog_locks"][cog_name] = channel_ids
            await self.config.guild(ctx.guild).cog_locks.set(conf["cog_locks"])
            channel_mentions = ", ".join(channel.mention for channel in allowed_channels)
            await ctx.send(f"Cog `{cog_name}` is now locked to channels: {channel_mentions}")
        else:
            command: commands.Command = cog_or_command.cog_or_command
            command_name: str = command.qualified_name
            conf["command_locks"][command_name] = channel_ids
            await self.config.guild(ctx.guild).command_locks.set(conf["command_locks"])
            channel_mentions = ", ".join(channel.mention for channel in allowed_channels)
            await ctx.send(f"Command `{command_name}` is now locked to channels: {channel_mentions}")

    @commandlock.command(name="unlock", aliases=["remove", "rem", "del"])
    async def remove_lock(self, ctx: commands.Context, *, cog_or_command: CogCommandConverter):
        """Remove a lock from a cog or command, allowing it to be used in any channel."""
        conf = await self.config.guild(ctx.guild).all()

        if cog_or_command.is_cog:
            cog: commands.Cog = cog_or_command.cog_or_command
            cog_name: str = cog.qualified_name
            if cog_name in conf["cog_locks"]:
                del conf["cog_locks"][cog_name]
                await self.config.guild(ctx.guild).cog_locks.set(conf["cog_locks"])
                await ctx.send(f"Lock removed from cog `{cog_name}`. It can now be used in any channel.")
            else:
                await ctx.send(f"No lock found for cog `{cog_name}`.")
        else:
            command: commands.Command = cog_or_command.cog_or_command
            command_name: str = command.qualified_name
            if command_name in conf["command_locks"]:
                del conf["command_locks"][command_name]
                await self.config.guild(ctx.guild).command_locks.set(conf["command_locks"])
                await ctx.send(f"Lock removed from command `{command_name}`. It can now be used in any channel.")
            else:
                await ctx.send(f"No lock found for command `{command_name}`.")

    @commandlock.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context, cog_or_command: CogCommandConverter = None):
        """View the current lock settings for a cog or command.

        If no cog or command is specified, shows all locks for the server.

        If a cog is specified, shows the useable channels for that cog including individual command locks.
        If a command is specified, shows the useable channels for that command.
        """
        conf = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="CommandLock Settings", color=await ctx.embed_color())

        if conf["whitelisted_roles"]:
            roles = [
                ctx.guild.get_role(role_id)
                for role_id in conf["whitelisted_roles"]
                if ctx.guild.get_role(role_id) is not None
            ]
            if len(roles) != len(conf["whitelisted_roles"]):
                # Clean up invalid role IDs
                conf["whitelisted_roles"] = [role.id for role in roles]
                await self.config.guild(ctx.guild).whitelisted_roles.set(conf["whitelisted_roles"])
            role_mentions = ", ".join(role.mention for role in roles)
            embed.add_field(name="Whitelisted Roles", value=role_mentions, inline=False)
        if cog_or_command and cog_or_command.is_cog:
            cog: commands.Cog = cog_or_command.cog_or_command
            cog_name: str = cog.qualified_name
            if cog_name in conf["cog_locks"]:
                channel_ids = conf["cog_locks"][cog_name]
                channels = [
                    ctx.guild.get_channel_or_thread(channel_id)
                    for channel_id in channel_ids
                    if ctx.guild.get_channel_or_thread(channel_id) is not None
                ]
                if len(channels) != len(channel_ids):
                    # Clean up invalid channel IDs
                    conf["cog_locks"][cog_name] = [channel.id for channel in channels]
                    await self.config.guild(ctx.guild).cog_locks.set(conf["cog_locks"])
                channel_mentions = ", ".join(channel.mention for channel in channels)
                embed.add_field(name=f"Locked channels for cog '{cog_name}'", value=channel_mentions, inline=False)
            else:
                embed.add_field(name=f"Locked channels for cog '{cog_name}'", value="No locks set.", inline=False)
        elif cog_or_command and not cog_or_command.is_cog:
            command: commands.Command = cog_or_command.cog_or_command
            command_name: str = command.qualified_name
            if command_name in conf["command_locks"]:
                channel_ids = conf["command_locks"][command_name]
                channels = [
                    ctx.guild.get_channel_or_thread(channel_id)
                    for channel_id in channel_ids
                    if ctx.guild.get_channel_or_thread(channel_id) is not None
                ]
                if len(channels) != len(channel_ids):
                    # Clean up invalid channel IDs
                    conf["command_locks"][command_name] = [channel.id for channel in channels]
                    await self.config.guild(ctx.guild).command_locks.set(conf["command_locks"])
                channel_mentions = ", ".join(channel.mention for channel in channels)
                embed.add_field(
                    name=f"Locked channels for command '{command_name}'", value=channel_mentions, inline=False
                )
            else:
                embed.add_field(
                    name=f"Locked channels for command '{command_name}'", value="No locks set.", inline=False
                )
        else:
            # Display all locks for all cogs and commands as a summary
            buffer = StringIO()
            if conf["cog_locks"]:
                buffer.write("**Cog Locks:**\n")
                sorted_cogs = sorted(conf["cog_locks"].items())
                for cog_name, channel_ids in sorted_cogs:
                    channels = [
                        ctx.guild.get_channel_or_thread(channel_id)
                        for channel_id in channel_ids
                        if ctx.guild.get_channel_or_thread(channel_id) is not None
                    ]
                    if len(channels) != len(channel_ids):
                        # Clean up invalid channel IDs
                        conf["cog_locks"][cog_name] = [channel.id for channel in channels]
                        await self.config.guild(ctx.guild).cog_locks.set(conf["cog_locks"])
                    channel_mentions = ", ".join(channel.mention for channel in channels)
                    buffer.write(f"- `{cog_name}`: {channel_mentions}\n")
            if conf["command_locks"]:
                buffer.write("**Command Locks:**\n")
                sorted_commands = sorted(conf["command_locks"].items())
                for command_name, channel_ids in sorted_commands:
                    channels = [
                        ctx.guild.get_channel_or_thread(channel_id)
                        for channel_id in channel_ids
                        if ctx.guild.get_channel_or_thread(channel_id) is not None
                    ]
                    if len(channels) != len(channel_ids):
                        # Clean up invalid channel IDs
                        conf["command_locks"][command_name] = [channel.id for channel in channels]
                        await self.config.guild(ctx.guild).command_locks.set(conf["command_locks"])
                    channel_mentions = ", ".join(channel.mention for channel in channels)
                    buffer.write(f"- `{command_name}`: {channel_mentions}\n")
            embed.description = buffer.getvalue() or "No locks set."
        await ctx.send(embed=embed)

    @commandlock.command(name="toggelchannel", aliases=["toggle"])
    async def toggle_channel(
        self,
        ctx: commands.Context,
        channel: discord.abc.GuildChannel,
        *,
        cog_or_command: CogCommandConverter,
    ) -> None:
        """Toggle a channel for an existing cog or command lock.

        This quickly adds or removes a channel from the lock configuration.

        Example:
        `[p]commandlock toggle #channel MyCog`
        `[p]cmdlock toggle #channel mycommand`
        """
        conf = await self.config.guild(ctx.guild).all()

        if cog_or_command.is_cog:
            target: commands.Cog = cog_or_command.cog_or_command
            target_name: str = target.qualified_name
            lock_map = conf["cog_locks"]
            lock_key = "cog_locks"
            target_label = f"cog `{target_name}`"
        else:
            target_cmd: commands.Command = cog_or_command.cog_or_command
            target_name = target_cmd.qualified_name
            lock_map = conf["command_locks"]
            lock_key = "command_locks"
            target_label = f"command `{target_name}`"

        # Ensure entry exists
        channel_ids: list[int] = lock_map.get(target_name, [])

        if channel.id in channel_ids:
            channel_ids.remove(channel.id)
            action = "removed from"
        else:
            channel_ids.append(channel.id)
            action = "added to"

        lock_map[target_name] = channel_ids
        await getattr(self.config.guild(ctx.guild), lock_key).set(lock_map)

        if channel_ids:
            channels = [
                ctx.guild.get_channel_or_thread(ch_id)
                for ch_id in channel_ids
                if ctx.guild.get_channel_or_thread(ch_id) is not None
            ]
            channel_mentions = ", ".join(ch.mention for ch in channels)
            await ctx.send(
                f"Channel {channel.mention} has been {action} the lock for {target_label}.\n"
                f"Current allowed channels: {channel_mentions}"
            )
        else:
            await ctx.send(
                f"Channel {channel.mention} has been {action} the lock for {target_label}.\n"
                "No channels remain in the lock; this target is now effectively unlocked until channels are re-added."
            )
