import asyncio
import logging
import typing as t
from base64 import b64encode

import discord
from discord import app_commands
from discord.http import Route
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

log = logging.getLogger("red.vrt.whitelabel")
_ = Translator("Whitelabel", __file__)
ENDPOINT = "/guilds/{guild_id}/members/@me"


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class BotProfileGroup(app_commands.Group):
    """Manage bot's profile settings."""


@cog_i18n(_)
class Whitelabel(commands.Cog):
    """Allow server owners to set a custom bot avatar, banner and bio."""

    __author__ = "vertyco"
    __version__ = "1.0.1"
    set_bot_profile = BotProfileGroup(name="botprofile", description="Manage bot's bio, banner, and avatar.")

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(main_guild=0, main_role=0, disallowed_msg="")

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
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        pass

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()

    async def is_allowed(self, requesting_guild: discord.Guild) -> t.Tuple[bool, str]:
        main_guild_id = await self.config.main_guild()
        if not main_guild_id:
            return True, ""
        main_role_id = await self.config.main_role()
        if not main_role_id:
            return True, ""
        main_guild: discord.Guild = self.bot.get_guild(main_guild_id)
        if not main_guild:
            return True, ""
        main_role = main_guild.get_role(main_role_id)
        if not main_role:
            return True, ""
        # Get owner of requesting guild and check if the owner has the role in the main guild
        owner = requesting_guild.owner
        if not owner:
            return False, _("Could not determine the owner of this server!")
        member = main_guild.get_member(owner.id)
        if not member:
            msg = _("I could not find {} in the 'main' server!").format(owner.mention)
            invite = await self.get_guild_invite(main_guild)
            if invite:
                msg += _(" You can join the server here: {}").format(invite)
            return False, msg

        if main_role not in member.roles:
            disallowed_msg = await self.config.disallowed_msg()
            if not disallowed_msg:
                disallowed_msg = _(
                    "The owner ({}) of this server does not have the {} role in the {} server required to use this feature."
                ).format(owner.mention, f"`@{main_role.name}`", f"`{main_guild.name}`")
                invite = await self.get_guild_invite(main_guild)
                if invite:
                    disallowed_msg += _(" You can join the server here: {}").format(invite)
            else:
                kwargs = {
                    "owner_mention": owner.mention,
                    "owner_name": owner.name,
                    "role_name": main_role.name,
                    "main_guild": main_guild.name,
                }
                invite = await self.get_guild_invite(main_guild)
                if invite:
                    kwargs["invite"] = invite
                else:
                    kwargs["invite"] = _("(no invite available)")
                for k, v in kwargs.items():
                    key = "{" + k + "}"
                    disallowed_msg = disallowed_msg.replace(key, str(v))
            return False, disallowed_msg
        return True, ""

    async def get_guild_invite(self, guild: discord.Guild) -> t.Optional[str]:
        if "VANITY_URL" in guild.features and guild.me.guild_permissions.manage_guild:
            try:
                invite = await guild.vanity_invite()
                if invite:
                    return invite.url
            except discord.HTTPException:
                pass
        if guild.me.guild_permissions.manage_guild:
            try:
                invites = await guild.invites()
                if invites:
                    return invites[0].url
            except discord.HTTPException:
                pass
        if guild.me.guild_permissions.create_instant_invite:
            try:
                invite = await guild.text_channels[0].create_invite()
                return invite.url
            except (discord.HTTPException, IndexError):
                pass
        return None

    @set_bot_profile.command(name="avatar")
    @app_commands.describe(avatar="The avatar to set for the bot. Leave empty to reset to default.")
    @app_commands.checks.cooldown(1, 600, key=lambda i: (i.guild_id))
    async def set_avatar(self, interaction: discord.Interaction, avatar: t.Optional[discord.Attachment]):
        """Set the bot's avatar for this server."""
        route: Route = Route(method="PATCH", path=ENDPOINT.format(guild_id=interaction.guild_id))
        allowed, msg = await self.is_allowed(interaction.guild)
        if not allowed:
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.response.defer(thinking=True)
        if avatar:
            if not avatar.content_type or not avatar.content_type.startswith("image/"):
                return await interaction.edit_original_response(content=_("The provided attachment is not an image."))
            image_bytes = await avatar.read()
            imageb64 = b64encode(image_bytes).decode("utf-8")
            extension = avatar.content_type.split("/")[-1]
            image = f"data:image/{extension};base64,{imageb64}"
            txt = _("My avatar has been updated for this server!")
        else:
            default_avatar = self.bot.user.avatar
            if default_avatar is None:
                image = ""
                txt = _("I do not have a global avatar to reset to, so my avatar for this server has been cleared!")
            else:
                image_bytes = await default_avatar.read()
                imageb64 = b64encode(image_bytes).decode("utf-8")
                image = f"data:image/png;base64,{imageb64}"
                txt = _("My avatar for this server has been reset to my global avatar!")

        payload = {"avatar": image}
        try:
            await self.bot.http.request(route, json=payload)
            await interaction.edit_original_response(content=txt)
        except discord.HTTPException as e:
            text = e.text.replace("Invalid Form Body In avatar: ", "")
            await interaction.edit_original_response(content=_("Failed to update avatar: {}").format(text))

    @set_bot_profile.command(name="banner")
    @app_commands.describe(banner="The banner to set for the bot. Leave empty to reset to default.")
    @app_commands.checks.cooldown(1, 30, key=lambda i: (i.guild_id))
    async def set_banner(self, interaction: discord.Interaction, banner: t.Optional[discord.Attachment]):
        """Set the bot's banner for this server."""
        route: Route = Route(method="PATCH", path=ENDPOINT.format(guild_id=interaction.guild_id))
        allowed, msg = await self.is_allowed(interaction.guild)
        if not allowed:
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.response.defer(thinking=True)
        if banner:
            if not banner.content_type or not banner.content_type.startswith("image/"):
                return await interaction.edit_original_response(content=_("The provided attachment is not an image."))
            image_bytes = await banner.read()
            imageb64 = b64encode(image_bytes).decode("utf-8")
            extension = banner.content_type.split("/")[-1]
            image = f"data:image/{extension};base64,{imageb64}"
            txt = _("My banner has been updated for this server!")
        else:
            default_banner = self.bot.user.banner
            if default_banner is None:
                image = ""
                txt = _("I do not have a global banner to reset to, so my banner for this server has been cleared!")
            else:
                image_bytes = await default_banner.read()
                imageb64 = b64encode(image_bytes).decode("utf-8")
                image = f"data:image/png;base64,{imageb64}"
                txt = _("My banner for this server has been reset to my global banner!")
        payload = {"banner": image}
        try:
            await self.bot.http.request(route, json=payload)
            await interaction.edit_original_response(content=txt)
        except discord.HTTPException as e:
            await interaction.edit_original_response(content=_("Failed to update banner: {}").format(e))

    @set_bot_profile.command(name="bio")
    @app_commands.describe(bio="The bio to set for the bot. Leave empty to reset to default.")
    @app_commands.checks.cooldown(1, 30, key=lambda i: (i.guild_id))
    async def set_bio(self, interaction: discord.Interaction, bio: t.Optional[str]):
        """Set the bot's bio for this server."""
        route: Route = Route(method="PATCH", path=ENDPOINT.format(guild_id=interaction.guild_id))
        allowed, msg = await self.is_allowed(interaction.guild)
        if not allowed:
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.response.defer(thinking=True)
        if bio:
            if len(bio) > 190:
                return await interaction.edit_original_response(content=_("Bio cannot be longer than 190 characters."))
            txt = _("My bio has been updated for this server!")
        else:
            txt = _("My bio for this server has been reset to my global bio!")
        payload = {"bio": bio or ""}
        try:
            await self.bot.http.request(route, json=payload)
            await interaction.edit_original_response(content=txt)
        except discord.HTTPException as e:
            await interaction.edit_original_response(
                content=_("Failed to update bio: {}").format(f"({e.status}) {e.text}")
            )

    @commands.group(name="whitelabel")
    @commands.is_owner()
    @commands.guild_only()
    async def whitelabel(self, ctx: commands.Context):
        """Configuration for the whitelabel cog."""
        pass

    @whitelabel.command(name="view")
    async def whitelabel_view(self, ctx: commands.Context):
        """View the current configuration."""
        main_guild_id = await self.config.main_guild()
        main_role_id = await self.config.main_role()
        disallowed_msg = await self.config.disallowed_msg()
        main_guild = self.bot.get_guild(main_guild_id) if main_guild_id else None
        main_role = main_guild.get_role(main_role_id) if main_guild and main_role_id else None
        embed = discord.Embed(title=_("Whitelabel Configuration"), color=await ctx.embed_color())
        embed.add_field(name=_("Main Guild"), value=f"{main_guild} ({main_guild_id})" if main_guild else _("Not set"))
        embed.add_field(name=_("Main Role"), value=f"{main_role} ({main_role_id})" if main_role else _("Not set"))
        embed.add_field(name=_("Disallowed Message"), value=disallowed_msg or _("Not set"), inline=False)
        await ctx.send(embed=embed)

    @whitelabel.command(name="mainserver")
    async def mainserver(self, ctx: commands.Context):
        """Set THIS server as the main server."""
        await self.config.main_guild.set(ctx.guild.id)
        await ctx.send(_("Main server has been set to: `{}`").format(ctx.guild.name))

    @whitelabel.command(name="mainrole")
    @commands.guild_only()
    async def mainrole(self, ctx: commands.Context, role: t.Optional[discord.Role] = None):
        """Set the role required in the main server for owners of other servers to change the bot's profile.

        Leave the role empty to disable the role check.
        """
        main_guild_id = await self.config.main_guild()
        main_guild = self.bot.get_guild(main_guild_id)
        if not main_guild:
            return await ctx.send(
                _("The main server is not set. Please set it using `{}whitelabel mainserver`").format(ctx.clean_prefix)
            )
        if ctx.guild.id != main_guild.id:
            return await ctx.send(
                _("You can only set the main role from the main server: `{}`").format(main_guild.name)
            )

        if role is None:
            await self.config.main_role.set(0)
            return await ctx.send(_("Main role has been cleared. Any server owner can now change the bot's profile."))

        if role.guild.id != main_guild.id:
            return await ctx.send(_("The role must be from the main server: `{}`").format(main_guild.name))
        await self.config.main_role.set(role.id)
        await ctx.send(_("Main role has been set to: `{}`").format(role.name))

    @whitelabel.command(name="disallowedmsg")
    async def disallowedmsg(self, ctx: commands.Context, *, message: str):
        """Set the message to send when a server owner is not allowed to change the bot's profile.

        You can use the following placeholders in your message:
        {owner_mention} - Mentions the owner of the server
        {owner_name} - The name of the owner of the server
        {role_name} - The name of the required role in the main server
        {main_guild} - The name of the main server
        {invite} - An invite link to the main server (if available)
        """
        if len(message) > 1000:
            return await ctx.send(_("The disallowed message cannot be longer than 1000 characters."))
        await self.config.disallowed_msg.set(message)
        await ctx.send(_("Disallowed message has been set."))

    @whitelabel.command(name="cleanup")
    async def cleanup(self, ctx: commands.Context):
        """
        Revert any unauthorized server profiles for users that no longer have access.

        WARNING: This will take a while to run and may hit rate limits if the bot is in many servers.
        """
        main_guild_id = await self.config.main_guild()
        if not main_guild_id:
            return await ctx.send(
                _("The main server is not set. Please set it using `{}whitelabel mainserver`.").format(ctx.clean_prefix)
            )
        main_guild = self.bot.get_guild(main_guild_id)
        if not main_guild:
            return await ctx.send(_("I am not in the main server. Please check my servers."))
        main_role_id = await self.config.main_role()
        if not main_role_id:
            return await ctx.send(
                _("The main role is not set. Please set it using `{}whitelabel mainrole`.").format(ctx.clean_prefix)
            )
        main_role = main_guild.get_role(main_role_id)
        if not main_role:
            return await ctx.send(_("The main role does not exist in the main server. Please check the role."))

        reverted = 0
        failed = 0
        msg = await ctx.send(_("Starting cleanup, this may take a while..."))
        async with ctx.typing():
            for guild in self.bot.guilds:
                if guild.id == main_guild.id:
                    continue
                allowed, __ = await self.is_allowed(guild)
                if allowed:
                    continue
                route: Route = Route(method="PATCH", path=ENDPOINT.format(guild.id))
                data = {}
                if guild.me.display_avatar.url != self.bot.user.display_avatar.url:
                    data["avatar"] = ""
                if guild.me.display_banner and not self.bot.user.banner:
                    data["banner"] = ""
                elif guild.me.display_banner != self.bot.user.banner:
                    data["banner"] = ""

                if "avatar" in data or "banner" in data:
                    data["bio"] = ""

                try:
                    await self.bot.http.request(route, json=data)
                    reverted += 1
                except discord.HTTPException:
                    failed += 1
                await asyncio.sleep(0.5)  # Add delay to avoid rate limits
            await msg.edit(content=_("Cleanup complete. Reverted: {} | Failed: {}").format(reverted, failed))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Check if a server owner lost the required role and revert the bot's profile if so."""
        main_guild = self.bot.get_guild(await self.config.main_guild())
        if not main_guild:
            return
        if before.guild.id != main_guild.id:
            return
        main_role = main_guild.get_role(await self.config.main_role())
        if not main_role:
            return
        if main_role in before.roles and main_role not in after.roles:
            log.warning("Member %s lost the main role %s", after, main_role)
            # Role was removed
            for guild in self.bot.guilds:
                if guild.owner_id != after.id:
                    continue
                route: Route = Route(method="PATCH", path=ENDPOINT.format(guild.id))
                try:
                    data = {"avatar": "", "banner": "", "bio": ""}
                    await self.bot.http.request(route, json=data)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Check if a server owner left the main guild and revert the bot's profile if so."""
        main_guild = self.bot.get_guild(await self.config.main_guild())
        if not main_guild:
            return
        if member.guild.id != main_guild.id:
            return
        main_role = main_guild.get_role(await self.config.main_role())
        if not main_role:
            return
        if main_role in member.roles:
            log.warning("Member %s left the main guild %s", member, main_guild)
            # Member had the role and left the guild
            for guild in self.bot.guilds:
                if guild.owner_id != member.id:
                    continue
                route: Route = Route(method="PATCH", path=ENDPOINT.format(guild.id))
                try:
                    data = {"avatar": "", "banner": "", "bio": ""}
                    await self.bot.http.request(route, json=data)
                except discord.HTTPException:
                    pass
