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

from .common.constants import (
    MODEL_LABELS,
    MODEL_ORDER,
    QUALITY_LABELS,
    QUALITY_ORDER,
    SIZE_LABELS,
    SIZE_ORDER,
    TIER_PRESETS,
    VALID_FORMATS,
    VALID_MODELS,
    VALID_QUALITIES,
    VALID_SIZES,
    format_cost,
    get_generation_cost,
)
from .common.models import DB, AccessLimits, GuildSettings
from .views import (
    AccessConfigView,
    EditImageButton,
    EditImageModal,
    SetApiKeyView,
    create_image_embed,
)

log = logging.getLogger("red.vrt.imgen")


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

    ok, reason, allowed_models, allowed_sizes, allowed_qualities, _access = cog._get_user_option_limits(
        conf, interaction.user
    )
    if not ok:
        return await interaction.response.send_message(reason, ephemeral=True)

    default_model = conf.default_model if conf.default_model in allowed_models else allowed_models[0]
    default_size = conf.default_size if conf.default_size in allowed_sizes else allowed_sizes[0]
    default_quality = conf.default_quality if conf.default_quality in allowed_qualities else allowed_qualities[0]

    # Use the first image attachment
    image_url = image_attachments[0].url

    # Open the edit modal with the image URL and config defaults
    modal = EditImageModal(
        cog,
        reference_image_url=image_url,
        allowed_models=allowed_models,
        allowed_sizes=allowed_sizes,
        allowed_qualities=allowed_qualities,
        default_model=default_model,
        default_size=default_size,
        default_quality=default_quality,
        default_output_format="png",
    )
    await interaction.response.send_modal(modal)


class ImGen(commands.Cog):
    """
    Create and edit images with OpenAI's GPT-Image models.

    Generate images from text prompts or edit existing images using AI.
    Supports turn-based editing where you can iteratively refine images.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.4.0"

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

    def _normalize_allowed(self, allowed: set[str] | None, valid: list[str]) -> list[str]:
        if allowed is None:
            return [value for value in valid]
        return [value for value in valid if value in allowed]

    def _get_user_option_limits(
        self, conf: GuildSettings, member: discord.Member
    ) -> tuple[bool, str, list[str], list[str], list[str], AccessLimits]:
        access = conf.get_access_limits(member)
        if not access.has_access:
            return False, "You don't have a role that allows image generation.", [], [], [], access

        allowed_models = self._normalize_allowed(access.allowed_models, MODEL_ORDER)
        allowed_sizes = self._normalize_allowed(access.allowed_sizes, SIZE_ORDER)
        allowed_qualities = self._normalize_allowed(access.allowed_qualities, QUALITY_ORDER)

        if access.allowed_sizes is not None:
            allowed_sizes = [size for size in allowed_sizes if size != "auto"]
        if access.allowed_qualities is not None:
            allowed_qualities = [quality for quality in allowed_qualities if quality != "auto"]

        if access.allowed_models is not None and not allowed_models:
            return (
                False,
                "No models are available for your roles. Ask an admin to configure access.",
                [],
                [],
                [],
                access,
            )
        if access.allowed_sizes is not None and not allowed_sizes:
            return False, "No sizes are available for your roles. Ask an admin to configure access.", [], [], [], access
        if access.allowed_qualities is not None and not allowed_qualities:
            return (
                False,
                "No quality options are available for your roles. Ask an admin to configure access.",
                [],
                [],
                [],
                access,
            )

        return True, "", allowed_models, allowed_sizes, allowed_qualities, access

    def _resolve_request_options(
        self,
        conf: GuildSettings,
        member: discord.Member,
        model: str | None,
        size: str | None,
        quality: str | None,
    ) -> tuple[bool, str, str, str, str, AccessLimits]:
        ok, reason, allowed_models, allowed_sizes, allowed_qualities, access = self._get_user_option_limits(
            conf, member
        )
        if not ok:
            return False, reason, "", "", "", access

        resolved_model = model or conf.default_model
        if resolved_model not in VALID_MODELS:
            return False, "Invalid model selection.", "", "", "", access

        if access.allowed_models is not None and resolved_model not in allowed_models:
            if model is None:
                if conf.default_model in allowed_models:
                    resolved_model = conf.default_model
                elif allowed_models:
                    resolved_model = allowed_models[0]
                else:
                    return (
                        False,
                        "No models are available for your roles. Ask an admin to configure access.",
                        "",
                        "",
                        "",
                        access,
                    )
            else:
                return False, "That model is not available for your role.", "", "", "", access

        resolved_size = size or conf.default_size
        if resolved_size not in VALID_SIZES:
            return False, "Invalid size selection.", "", "", "", access

        if access.allowed_sizes is not None:
            if resolved_size == "auto":
                if conf.default_size in allowed_sizes:
                    resolved_size = conf.default_size
                elif allowed_sizes:
                    resolved_size = allowed_sizes[0]
                else:
                    return (
                        False,
                        "No sizes are available for your roles. Ask an admin to configure access.",
                        "",
                        "",
                        "",
                        access,
                    )
            elif resolved_size not in allowed_sizes:
                return False, "That size is not available for your role.", "", "", "", access

        resolved_quality = quality or conf.default_quality
        if resolved_quality not in VALID_QUALITIES:
            return False, "Invalid quality selection.", "", "", "", access

        if access.allowed_qualities is not None:
            if resolved_quality == "auto":
                if conf.default_quality in allowed_qualities:
                    resolved_quality = conf.default_quality
                elif allowed_qualities:
                    resolved_quality = allowed_qualities[0]
                else:
                    return (
                        False,
                        "No quality options are available for your roles. Ask an admin to configure access.",
                        "",
                        "",
                        "",
                        access,
                    )
            elif resolved_quality not in allowed_qualities:
                return False, "That quality setting is not available for your role.", "", "", "", access

        return True, "", resolved_model, resolved_size, resolved_quality, access

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
        can_gen, reason = conf.can_generate(interaction.user)
        if not can_gen:
            await interaction.followup.send(reason, ephemeral=True)
            return False

        ok, reason, resolved_model, resolved_size, resolved_quality, _access = self._resolve_request_options(
            conf,
            interaction.user,
            model,
            size,
            quality,
        )
        if not ok:
            await interaction.followup.send(reason, ephemeral=True)
            return False

        client = self.get_openai_client(conf)

        if not client:
            await interaction.followup.send(
                "OpenAI API key not configured. An admin needs to run `/imgen api` to set it up.",
                ephemeral=True,
            )
            return False

        try:
            is_edit = reference_images is not None and len(reference_images) > 0
            # GPT image models support "auto" for size directly
            actual_size = resolved_size if resolved_size != "auto" else "auto"

            if is_edit:
                # Use images.edit endpoint for editing
                response: ImagesResponse = await client.images.edit(
                    model=resolved_model,
                    image=reference_images,
                    prompt=prompt,
                    size=actual_size,
                    quality=resolved_quality,
                    output_format=output_format,
                    n=1,
                )
                title = "✏️ Edited Image"
            else:
                # Use images.generate endpoint for new images
                response = await client.images.generate(
                    model=resolved_model,
                    prompt=prompt,
                    size=actual_size,
                    quality=resolved_quality,
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
                model=resolved_model,
                size=resolved_size,
                quality=resolved_quality,
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
                    log_embed.add_field(name="Model", value=resolved_model, inline=True)
                    log_embed.add_field(name="Size", value=resolved_size, inline=True)
                    log_embed.add_field(name="Quality", value=resolved_quality, inline=True)
                    # Add cost to log
                    cost = get_generation_cost(resolved_model, resolved_quality, resolved_size)
                    if cost > 0:
                        log_embed.add_field(name="Cost", value=format_cost(cost), inline=True)
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

    async def _autocomplete_models(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        conf = self.db.get_conf(interaction.guild)
        ok, _reason, allowed_models, _allowed_sizes, _allowed_qualities, _access = self._get_user_option_limits(
            conf, interaction.user
        )
        if not ok:
            return []
        needle = current.lower()
        choices = []
        for value in allowed_models:
            label = MODEL_LABELS.get(value, value)
            if needle in value.lower() or needle in label.lower():
                choices.append(app_commands.Choice(name=label, value=value))
        return choices[:25]

    async def _autocomplete_sizes(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        conf = self.db.get_conf(interaction.guild)
        ok, _reason, _allowed_models, allowed_sizes, _allowed_qualities, _access = self._get_user_option_limits(
            conf, interaction.user
        )
        if not ok:
            return []
        needle = current.lower()
        choices = []
        for value in allowed_sizes:
            label = SIZE_LABELS.get(value, value)
            if needle in value.lower() or needle in label.lower():
                choices.append(app_commands.Choice(name=label, value=value))
        return choices[:25]

    async def _autocomplete_qualities(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        conf = self.db.get_conf(interaction.guild)
        ok, _reason, _allowed_models, _allowed_sizes, allowed_qualities, _access = self._get_user_option_limits(
            conf, interaction.user
        )
        if not ok:
            return []
        needle = current.lower()
        choices = []
        for value in allowed_qualities:
            label = QUALITY_LABELS.get(value, value)
            if needle in value.lower() or needle in label.lower():
                choices.append(app_commands.Choice(name=label, value=value))
        return choices[:25]

    @app_commands.command(name="makeimage", description="Generate an image from a text prompt")
    @app_commands.describe(
        prompt="Describe the image you want to generate",
        model="The model to use for generation",
        size="Size of the generated image",
        quality="Quality level of the image",
        output_format="Output image format",
    )
    @app_commands.choices(output_format=[app_commands.Choice(name=f, value=f) for f in VALID_FORMATS])
    @app_commands.guild_only()
    @app_commands.autocomplete(model=_autocomplete_models)
    @app_commands.autocomplete(size=_autocomplete_sizes)
    @app_commands.autocomplete(quality=_autocomplete_qualities)
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
    @app_commands.choices(output_format=[app_commands.Choice(name=f, value=f) for f in VALID_FORMATS])
    @app_commands.guild_only()
    @app_commands.autocomplete(model=_autocomplete_models)
    @app_commands.autocomplete(size=_autocomplete_sizes)
    @app_commands.autocomplete(quality=_autocomplete_qualities)
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

        # Role access
        if conf.role_cooldowns:
            role_lines = []
            for rid, rc in conf.role_cooldowns.items():
                role = interaction.guild.get_role(rid)
                if not role:
                    continue
                cooldown_txt = f"{rc.cooldown_seconds}s" if rc.cooldown_seconds > 0 else "No cooldown"
                models_txt = (
                    "All models"
                    if not rc.allowed_models
                    else ", ".join(MODEL_LABELS.get(value, value) for value in rc.allowed_models)
                )
                sizes_txt = (
                    "All sizes (auto)"
                    if not rc.allowed_sizes
                    else ", ".join(SIZE_LABELS.get(value, value) for value in rc.allowed_sizes)
                )
                qualities_txt = (
                    "All qualities (auto)"
                    if not rc.allowed_qualities
                    else ", ".join(QUALITY_LABELS.get(value, value) for value in rc.allowed_qualities)
                )

                # Calculate cost range
                models = rc.allowed_models or VALID_MODELS
                sizes = rc.allowed_sizes or [s for s in VALID_SIZES if s != "auto"]
                qualities = rc.allowed_qualities or [q for q in VALID_QUALITIES if q != "auto"]
                costs: list[float] = []
                for model in models:
                    for quality in qualities:
                        for size in sizes:
                            cost = get_generation_cost(model, quality, size)
                            if cost > 0:
                                costs.append(cost)
                if costs:
                    min_cost, max_cost = min(costs), max(costs)
                    cost_txt = (
                        format_cost(min_cost)
                        if min_cost == max_cost
                        else f"{format_cost(min_cost)} - {format_cost(max_cost)}"
                    )
                else:
                    cost_txt = "N/A"

                role_lines.append(
                    f"{role.mention}: {cooldown_txt}\n"
                    f"• Models: {models_txt}\n"
                    f"• Sizes: {sizes_txt}\n"
                    f"• Qualities: {qualities_txt}\n"
                    f"• Cost/image: {cost_txt}"
                )
            embed.add_field(
                name="Allowed Roles & Access",
                value="\n\n".join(role_lines) if role_lines else "Roles configured but not found",
                inline=False,
            )
        else:
            embed.add_field(
                name="Access Control",
                value="🌐 Open access (no role restrictions)",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @imgen.command(name="access", description="Manage role-based access rules")
    async def imgen_access(self, interaction: discord.Interaction):
        """Open the access management menu."""
        view = AccessConfigView(self, interaction.guild)
        await interaction.response.send_message(view=view, ephemeral=True)

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

    @imgen.command(name="tiers", description="View available subscription tier presets")
    async def imgen_tiers(self, interaction: discord.Interaction):
        """View available tier presets and their configurations."""
        conf = self.db.get_conf(interaction.guild)

        # Build a mapping of tier -> roles that match it
        tier_roles: dict[str, list[discord.Role]] = {tid: [] for tid in TIER_PRESETS}
        for role_id, rc in conf.role_cooldowns.items():
            role = interaction.guild.get_role(role_id)
            if not role:
                continue
            # Check which tier this role matches
            for tid, tier in TIER_PRESETS.items():
                if (
                    set(rc.allowed_models or []) == set(tier.models)
                    and set(rc.allowed_qualities or []) == set(tier.qualities)
                    and set(rc.allowed_sizes or []) == set(tier.sizes)
                    and rc.cooldown_seconds == tier.cooldown_seconds
                ):
                    tier_roles[tid].append(role)
                    break

        embed = discord.Embed(
            title="🎨 Subscription Tier Presets",
            description=(
                "Use `/imgen tier` to apply a preset to a role.\n"
                "These presets provide balanced access levels for subscription tiers."
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(tz=timezone.utc),
        )

        for tier_id, tier in TIER_PRESETS.items():
            min_cost, max_cost = tier.get_cost_range()
            cost_txt = (
                format_cost(min_cost) if min_cost == max_cost else f"{format_cost(min_cost)} - {format_cost(max_cost)}"
            )

            models_txt = ", ".join(MODEL_LABELS.get(m, m) for m in tier.models)
            qualities_txt = ", ".join(QUALITY_LABELS.get(q, q) for q in tier.qualities)
            sizes_txt = ", ".join(SIZE_LABELS.get(s, s) for s in tier.sizes)

            cooldown_txt = (
                f"{tier.cooldown_seconds}s" if tier.cooldown_seconds < 60 else f"{tier.cooldown_seconds // 60}m"
            )

            # Show roles configured for this tier
            roles_txt = ""
            if tier_roles[tier_id]:
                role_mentions = ", ".join(r.mention for r in tier_roles[tier_id])
                roles_txt = f"\n**Roles:** {role_mentions}"

            value = (
                f"*{tier.description}*\n"
                f"**Models:** {models_txt}\n"
                f"**Qualities:** {qualities_txt}\n"
                f"**Sizes:** {sizes_txt}\n"
                f"**Cooldown:** {cooldown_txt}\n"
                f"**Cost/image:** {cost_txt}"
                f"{roles_txt}"
            )
            embed.add_field(name=f"{tier.emoji} {tier.name} (`{tier_id}`)", value=value, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @imgen.command(name="tier", description="Apply a subscription tier preset to a role")
    @app_commands.describe(
        role="The role to configure",
        tier="The tier preset to apply",
    )
    @app_commands.choices(
        tier=[app_commands.Choice(name=f"{t.emoji} {t.name}", value=tid) for tid, t in TIER_PRESETS.items()]
    )
    async def imgen_tier(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        tier: str,
    ):
        """Apply a subscription tier preset to a role."""
        from .common.models import RoleCooldown

        preset = TIER_PRESETS.get(tier)
        if not preset:
            return await interaction.response.send_message("Invalid tier selected.", ephemeral=True)

        conf = self.db.get_conf(interaction.guild)
        conf.role_cooldowns[role.id] = RoleCooldown(
            role_id=role.id,
            cooldown_seconds=preset.cooldown_seconds,
            allowed_models=preset.models,
            allowed_sizes=preset.sizes,
            allowed_qualities=preset.qualities,
        )
        await self.save()

        min_cost, max_cost = preset.get_cost_range()
        cost_txt = (
            format_cost(min_cost) if min_cost == max_cost else f"{format_cost(min_cost)} - {format_cost(max_cost)}"
        )

        embed = discord.Embed(
            title=f"{preset.emoji} Applied {preset.name} Tier",
            description=f"Successfully applied the **{preset.name}** tier to {role.mention}.",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Configuration",
            value=(
                f"**Models:** {', '.join(MODEL_LABELS.get(m, m) for m in preset.models)}\n"
                f"**Qualities:** {', '.join(QUALITY_LABELS.get(q, q) for q in preset.qualities)}\n"
                f"**Sizes:** {', '.join(SIZE_LABELS.get(s, s) for s in preset.sizes)}\n"
                f"**Cooldown:** {preset.cooldown_seconds}s\n"
                f"**Cost/image:** {cost_txt}"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
