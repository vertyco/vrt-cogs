import asyncio
import base64
import logging
import typing as t
from contextlib import suppress
from datetime import datetime, timezone
from io import BytesIO

import discord
from discord import app_commands
from openai import AsyncOpenAI
from openai.types import ImagesResponse
from pydantic import ValidationError
from redbot.core import Config, commands
from redbot.core.bot import Red

from .common.models import DB, GuildSettings, RoleCooldown
from .views import EditImageButton, EditImageModal, SetApiKeyView, create_image_embed

log = logging.getLogger("red.vrt.imgen")

# Valid options for gpt-image models
VALID_SIZES = ["auto", "1024x1024", "1536x1024", "1024x1536"]
VALID_QUALITIES = ["auto", "low", "medium", "high"]
VALID_FORMATS = ["png", "jpeg", "webp"]
VALID_MODELS = ["gpt-image-1.5", "gpt-image-1-mini"]


@app_commands.context_menu(name="Edit Image")
@app_commands.guild_only()
async def edit_image_context_menu(interaction: discord.Interaction, message: discord.Message):
    """Edit an image from a message using AI."""
    # Check if message has image attachments
    image_attachments = [a for a in message.attachments if a.content_type and a.content_type.startswith("image/")]
    if not image_attachments:
        return await interaction.response.send_message(
            "❌ This message doesn't contain any image attachments.",
            ephemeral=True,
        )

    bot: Red = interaction.client
    cog: t.Optional["ImGen"] = bot.get_cog("ImGen")
    if not cog:
        return await interaction.response.send_message("ImGen cog is not loaded.", ephemeral=True)

    # Check if user can generate
    conf = cog.db.get_conf(interaction.guild)
    can_gen, reason = conf.can_generate(interaction.user)
    if not can_gen:
        return await interaction.response.send_message(reason, ephemeral=True)

    # Use the first image attachment
    image_url = image_attachments[0].url

    # Open the edit modal with the image URL and config defaults
    modal = EditImageModal(
        cog,
        reference_image_url=image_url,
        default_model=conf.default_model,
        default_size=conf.default_size,
    )
    await interaction.response.send_modal(modal)


class ImGen(commands.Cog):
    """
    Create and edit images with OpenAI's GPT-Image models.

    Generate images from text prompts or edit existing images using AI.
    Supports turn-based editing where you can iteratively refine images.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()
        self.saving = False
        self.initialized = False

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        """Delete cooldown data for user."""
        for conf in self.db.configs.values():
            if user_id in conf.user_cooldowns:
                del conf.user_cooldowns[user_id]
        await self.save()

    async def red_get_data_for_user(self, *, requester: str, user_id: int):
        """No meaningful user data stored."""
        return {}

    async def cog_load(self) -> None:
        self.bot.tree.add_command(edit_image_context_menu)
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(edit_image_context_menu.name, type=edit_image_context_menu.type)
        await self.save()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        try:
            self.db = await asyncio.to_thread(DB.model_validate, data)
        except ValidationError:
            log.warning("Failed to validate config, starting fresh")
            self.db = DB()
        log.info("Config loaded")

        # Register dynamic items for persistent views
        self.bot.add_dynamic_items(EditImageButton)

        self.initialized = True
        log.info("ImGen initialized")

    async def save(self) -> None:
        if self.saving:
            return
        if not self.initialized:
            log.warning("Attempted to save before initialization")
            return
        try:
            self.saving = True
            dump = await asyncio.to_thread(self.db.model_dump)
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    def get_openai_client(self, conf: GuildSettings) -> t.Optional[AsyncOpenAI]:
        """Get the OpenAI client with the guild's configured API key."""
        if not conf.api_key:
            return None
        return AsyncOpenAI(api_key=conf.api_key)

    async def generate_image(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: str | None = None,
        size: str = "auto",
        quality: str = "auto",
        output_format: str = "png",
        reference_images: list[tuple[str, bytes, str]] | None = None,
    ) -> bool:
        """Generate or edit an image using OpenAI's Images API.

        Args:
            reference_images: List of tuples (filename, bytes, content_type) for editing
        """
        conf = self.db.get_conf(interaction.guild)
        client = self.get_openai_client(conf)
        model = model or conf.default_model

        if not client:
            await interaction.followup.send(
                "OpenAI API key not configured. An admin needs to run `/imgen api` to set it up.",
                ephemeral=True,
            )
            return False

        try:
            is_edit = reference_images is not None and len(reference_images) > 0
            # GPT image models support "auto" for size directly
            actual_size = size if size != "auto" else "auto"

            if is_edit:
                # Use images.edit endpoint for editing
                response: ImagesResponse = await client.images.edit(
                    model=model,
                    image=reference_images,
                    prompt=prompt,
                    size=actual_size,
                    quality=quality,
                    output_format=output_format,
                    n=1,
                )
                title = "✏️ Edited Image"
            else:
                # Use images.generate endpoint for new images
                response = await client.images.generate(
                    model=model,
                    prompt=prompt,
                    size=actual_size,
                    quality=quality,
                    output_format=output_format,
                    n=1,
                )
                title = "🎨 Generated Image"

            # GPT image models always return base64-encoded images
            if not response.data or not response.data[0].b64_json:
                await interaction.followup.send(
                    "No image was generated. The API may have refused the prompt or encountered an error.",
                    ephemeral=True,
                )
                return False

            image_bytes = base64.b64decode(response.data[0].b64_json)
            file = discord.File(BytesIO(image_bytes), filename=f"generated.{output_format}")

            # Create the embed
            embed = create_image_embed(
                prompt=prompt,
                model=model,
                size=size,
                quality=quality,
                author=interaction.user,
                title=title,
            )
            embed.set_image(url=f"attachment://generated.{output_format}")

            # Create view with edit button (no response_id needed anymore)
            view = discord.ui.View(timeout=None)
            view.add_item(EditImageButton().item)

            # Send the image
            message = await interaction.followup.send(embed=embed, file=file, view=view)

            # Record the generation for cooldown tracking
            conf.record_generation(interaction.user)
            await self.save()

            # Log to logging channel if configured
            if conf.log_channel:
                log_channel = interaction.guild.get_channel(conf.log_channel)
                if log_channel and isinstance(log_channel, discord.TextChannel):
                    log_title = "✏️ Image Edited" if is_edit else "🎨 Image Generated"
                    log_embed = discord.Embed(
                        title=log_title,
                        description=f"**User:** {interaction.user.mention}\n**Prompt:** {prompt[:1000]}{'...' if len(prompt) > 1000 else ''}",
                        color=discord.Color.blue(),
                        timestamp=datetime.now(tz=timezone.utc),
                    )
                    log_embed.add_field(name="Model", value=model, inline=True)
                    log_embed.add_field(name="Size", value=size, inline=True)
                    log_embed.add_field(name="Quality", value=quality, inline=True)
                    if message:
                        log_embed.add_field(name="Message", value=f"[Jump]({message.jump_url})", inline=True)
                    with suppress(discord.HTTPException):
                        await log_channel.send(embed=log_embed)

            return True

        except Exception as e:
            log.exception("Error generating image", exc_info=e)
            error_msg = str(e)
            if len(error_msg) > 1900:
                error_msg = error_msg[:1900] + "..."
            await interaction.followup.send(f"Error generating image: {error_msg}", ephemeral=True)
            return False

    # ==================== SLASH COMMANDS ====================

    @app_commands.command(name="makeimage", description="Generate an image from a text prompt")
    @app_commands.describe(
        prompt="Describe the image you want to generate",
        model="The model to use for generation",
        size="Size of the generated image",
        quality="Quality level of the image",
        output_format="Output image format",
    )
    @app_commands.choices(
        model=[app_commands.Choice(name=m, value=m) for m in VALID_MODELS],
        size=[app_commands.Choice(name=s, value=s) for s in VALID_SIZES],
        quality=[app_commands.Choice(name=q, value=q) for q in VALID_QUALITIES],
        output_format=[app_commands.Choice(name=f, value=f) for f in VALID_FORMATS],
    )
    @app_commands.guild_only()
    async def makeimage(
        self,
        interaction: discord.Interaction,
        prompt: str,
        model: str | None = None,
        size: str = "auto",
        quality: str = "auto",
        output_format: str = "png",
    ):
        """Generate an image from a text prompt."""
        # Check access
        conf = self.db.get_conf(interaction.guild)
        can_gen, reason = conf.can_generate(interaction.user)
        if not can_gen:
            return await interaction.response.send_message(reason, ephemeral=True)

        await interaction.response.defer()

        await self.generate_image(
            interaction=interaction,
            prompt=prompt,
            model=model,
            size=size,
            quality=quality,
            output_format=output_format,
        )

    @app_commands.command(name="editimage", description="Edit an existing image using AI")
    @app_commands.describe(
        prompt="Describe how you want to modify the image",
        image="The main image to edit (required)",
        image2="Additional reference image (optional)",
        image3="Additional reference image (optional)",
        model="The model to use for editing",
        size="Size of the output image",
        quality="Quality level of the image",
        output_format="Output image format",
    )
    @app_commands.choices(
        model=[app_commands.Choice(name=m, value=m) for m in VALID_MODELS],
        size=[app_commands.Choice(name=s, value=s) for s in VALID_SIZES],
        quality=[app_commands.Choice(name=q, value=q) for q in VALID_QUALITIES],
        output_format=[app_commands.Choice(name=f, value=f) for f in VALID_FORMATS],
    )
    @app_commands.guild_only()
    async def editimage(
        self,
        interaction: discord.Interaction,
        prompt: str,
        image: discord.Attachment,
        image2: discord.Attachment | None = None,
        image3: discord.Attachment | None = None,
        model: str | None = None,
        size: str = "auto",
        quality: str = "auto",
        output_format: str = "png",
    ):
        """Edit an existing image with AI assistance."""
        # Check access
        conf = self.db.get_conf(interaction.guild)
        can_gen, reason = conf.can_generate(interaction.user)
        if not can_gen:
            return await interaction.response.send_message(reason, ephemeral=True)

        await interaction.response.defer()

        # Collect all images with proper MIME type info
        reference_images: list[tuple[str, bytes, str]] = []
        for i, attachment in enumerate([image, image2, image3]):
            if attachment:
                try:
                    img_bytes = await attachment.read()
                    # Get content type from attachment
                    content_type = attachment.content_type or "image/png"
                    ext = content_type.split("/")[-1]
                    if ext == "jpeg":
                        ext = "jpg"
                    reference_images.append((f"image{i}.{ext}", img_bytes, content_type))
                except Exception as e:
                    log.warning(f"Failed to read attachment: {e}")
                    continue

        if not reference_images:
            return await interaction.followup.send("Failed to read the provided image.", ephemeral=True)

        await self.generate_image(
            interaction=interaction,
            prompt=prompt,
            model=model,
            size=size,
            quality=quality,
            output_format=output_format,
            reference_images=reference_images,
        )

    # ==================== ADMIN COMMANDS ====================

    imgen = app_commands.Group(
        name="imgen",
        description="Configure ImGen settings",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @imgen.command(name="view", description="View current ImGen settings")
    async def imgen_view(self, interaction: discord.Interaction):
        """View current settings."""
        conf = self.db.get_conf(interaction.guild)

        embed = discord.Embed(
            title="ImGen Settings",
            color=discord.Color.blue(),
            timestamp=datetime.now(tz=timezone.utc),
        )

        # API Key status
        api_status = "✅ Configured" if conf.api_key else "❌ Not set"
        embed.add_field(name="API Key", value=api_status, inline=True)

        # Log channel
        log_ch = interaction.guild.get_channel(conf.log_channel) if conf.log_channel else None
        embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set", inline=True)

        # Default settings
        embed.add_field(name="Default Model", value=conf.default_model, inline=True)
        embed.add_field(name="Default Size", value=conf.default_size, inline=True)
        embed.add_field(name="Default Quality", value=conf.default_quality, inline=True)

        # Role cooldowns / access
        if conf.role_cooldowns:
            role_lines = []
            for rid, rc in conf.role_cooldowns.items():
                role = interaction.guild.get_role(rid)
                if role:
                    cooldown_txt = f"{rc.cooldown_seconds}s" if rc.cooldown_seconds > 0 else "No cooldown"
                    role_lines.append(f"{role.mention}: {cooldown_txt}")
            embed.add_field(
                name="Allowed Roles & Cooldowns",
                value="\n".join(role_lines) if role_lines else "Roles configured but not found",
                inline=False,
            )
        else:
            embed.add_field(
                name="Access Control",
                value="🌐 Open access (no role restrictions)",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @imgen.command(name="api", description="Set the OpenAI API key for this server")
    async def imgen_api(self, interaction: discord.Interaction):
        """Set the OpenAI API key for image generation."""
        cog = self
        view = SetApiKeyView(cog)

        embed = discord.Embed(
            title="🔑 Set OpenAI API Key",
            description=(
                "Click the button below to set your OpenAI API key for this server.\n\n"
                "**How to get an API key:**\n"
                "1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)\n"
                "2. Create a new API key\n"
                "3. Copy the key and paste it in the modal\n\n"
                "⚠️ **Note:** Keep your API key secure. Each server needs its own key."
            ),
            color=discord.Color.blue(),
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @imgen.command(name="clearapi", description="Remove the OpenAI API key for this server")
    async def imgen_clearapi(self, interaction: discord.Interaction):
        """Remove the OpenAI API key."""
        conf = self.db.get_conf(interaction.guild)
        if not conf.api_key:
            return await interaction.response.send_message("No API key is configured.", ephemeral=True)

        conf.api_key = None
        await self.save()
        await interaction.response.send_message("✅ OpenAI API key has been removed.", ephemeral=True)

    @imgen.command(name="logchannel", description="Set or clear the logging channel")
    @app_commands.describe(channel="The channel to log generations to (leave empty to disable)")
    async def imgen_logchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ):
        """Set the channel for generation logs. Leave empty to disable."""
        conf = self.db.get_conf(interaction.guild)
        conf.log_channel = channel.id if channel else 0
        await self.save()

        if channel:
            await interaction.response.send_message(
                f"✅ Generation logs will be sent to {channel.mention}.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("✅ Generation logging disabled.", ephemeral=True)

    @imgen.command(name="addrole", description="Add a role to the allow list with a cooldown")
    @app_commands.describe(
        role="The role to add",
        cooldown_seconds="Seconds between generations for this role (0 = no cooldown)",
    )
    async def imgen_addrole(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        cooldown_seconds: int = 60,
    ):
        """Add a role that can use image generation."""
        if cooldown_seconds < 0:
            return await interaction.response.send_message(
                "Cooldown must be 0 or greater.",
                ephemeral=True,
            )

        conf = self.db.get_conf(interaction.guild)
        conf.role_cooldowns[role.id] = RoleCooldown(
            role_id=role.id,
            cooldown_seconds=cooldown_seconds,
        )
        await self.save()

        cooldown_txt = f"with a {cooldown_seconds}s cooldown" if cooldown_seconds > 0 else "with no cooldown"
        await interaction.response.send_message(
            f"✅ Added {role.mention} to the allow list {cooldown_txt}.",
            ephemeral=True,
        )

    @imgen.command(name="removerole", description="Remove a role from the allow list")
    @app_commands.describe(role="The role to remove")
    async def imgen_removerole(self, interaction: discord.Interaction, role: discord.Role):
        """Remove a role from the access list."""
        conf = self.db.get_conf(interaction.guild)

        if role.id not in conf.role_cooldowns:
            return await interaction.response.send_message(
                f"{role.mention} is not in the allow list.",
                ephemeral=True,
            )

        del conf.role_cooldowns[role.id]
        await self.save()
        await interaction.response.send_message(
            f"✅ Removed {role.mention} from the allow list.",
            ephemeral=True,
        )

    @imgen.command(name="clearroles", description="Clear all role restrictions (open access)")
    async def imgen_clearroles(self, interaction: discord.Interaction):
        """Clear all role restrictions, allowing open access."""
        conf = self.db.get_conf(interaction.guild)

        if not conf.role_cooldowns:
            return await interaction.response.send_message(
                "No role restrictions are currently configured.",
                ephemeral=True,
            )

        conf.role_cooldowns.clear()
        await self.save()
        await interaction.response.send_message(
            "✅ All role restrictions cleared. Image generation is now open to everyone.",
            ephemeral=True,
        )

    @imgen.command(name="defaults", description="Set default generation settings")
    @app_commands.describe(
        model="Default model for generation",
        size="Default image size",
        quality="Default image quality",
    )
    @app_commands.choices(
        model=[app_commands.Choice(name=m, value=m) for m in VALID_MODELS],
        size=[app_commands.Choice(name=s, value=s) for s in VALID_SIZES],
        quality=[app_commands.Choice(name=q, value=q) for q in VALID_QUALITIES],
    )
    async def imgen_defaults(
        self,
        interaction: discord.Interaction,
        model: str | None = None,
        size: str | None = None,
        quality: str | None = None,
    ):
        """Set default generation settings for the server."""
        conf = self.db.get_conf(interaction.guild)

        changes = []
        if model:
            conf.default_model = model
            changes.append(f"Model: `{model}`")
        if size:
            conf.default_size = size
            changes.append(f"Size: `{size}`")
        if quality:
            conf.default_quality = quality
            changes.append(f"Quality: `{quality}`")

        if not changes:
            return await interaction.response.send_message(
                "No changes specified. Use the options to set defaults.",
                ephemeral=True,
            )

        await self.save()
        await interaction.response.send_message(
            "✅ Updated default settings:\n" + "\n".join(changes),
            ephemeral=True,
        )
