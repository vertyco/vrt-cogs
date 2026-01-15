import logging
import re
import typing as t
from datetime import datetime, timezone

import discord
from redbot.core.bot import Red

from .common.constants import (
    MODEL_LABELS,
    QUALITY_LABELS,
    SIZE_LABELS,
    VALID_FORMATS,
    VALID_MODELS,
    VALID_QUALITIES,
    VALID_SIZES,
)
from .common.models import RoleCooldown

if t.TYPE_CHECKING:
    from .main import ImGen

log = logging.getLogger("red.vrt.imgen.views")


def _make_model_options(default: str, allowed_models: list[str]) -> list[discord.SelectOption]:
    """Create model options with the specified default."""
    return [
        discord.SelectOption(
            label=MODEL_LABELS.get(value, value),
            value=value,
            default=(value == default),
        )
        for value in allowed_models
    ]


def _make_size_options(default: str, allowed_sizes: list[str]) -> list[discord.SelectOption]:
    """Create size options with the specified default."""
    return [
        discord.SelectOption(
            label=SIZE_LABELS.get(value, value),
            value=value,
            default=(value == default),
        )
        for value in allowed_sizes
    ]


def _make_quality_options(default: str, allowed_qualities: list[str]) -> list[discord.SelectOption]:
    """Create quality options with the specified default."""
    return [
        discord.SelectOption(
            label=QUALITY_LABELS.get(value, value),
            value=value,
            default=(value == default),
        )
        for value in allowed_qualities
    ]


def _make_format_options(default: str = "png") -> list[discord.SelectOption]:
    """Create output format options with the specified default."""
    return [
        discord.SelectOption(label=value.upper(), value=value, default=(value == default)) for value in VALID_FORMATS
    ]


class EditImageModal(discord.ui.Modal):
    """Modal for editing an image with a new prompt and settings dropdowns."""

    def __init__(
        self,
        cog: "ImGen",
        reference_image_url: str,
        allowed_models: list[str],
        allowed_sizes: list[str],
        allowed_qualities: list[str],
        default_model: str = "gpt-image-1.5",
        default_size: str = "auto",
        default_quality: str = "auto",
        default_output_format: str = "png",
    ):
        super().__init__(title="Edit Image", timeout=300)
        self.cog = cog
        self.reference_image_url = reference_image_url

        # Create components with dynamic defaults
        self.prompt_input = discord.ui.TextInput(
            label="Edit Prompt",
            placeholder="Describe how you want to modify the image...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
        )
        self.add_item(self.prompt_input)

        model_select = discord.ui.Select(
            placeholder="Select model",
            options=_make_model_options(default_model, allowed_models),
        )
        self.model_label = discord.ui.Label(text="Model", component=model_select)
        self.add_item(self.model_label)

        size_select = discord.ui.Select(
            placeholder="Select image size",
            options=_make_size_options(default_size, allowed_sizes),
        )
        self.size_label = discord.ui.Label(text="Size", component=size_select)
        self.add_item(self.size_label)

        quality_select = discord.ui.Select(
            placeholder="Select image quality",
            options=_make_quality_options(default_quality, allowed_qualities),
        )
        self.quality_label = discord.ui.Label(text="Quality", component=quality_select)
        self.add_item(self.quality_label)

        format_select = discord.ui.Select(
            placeholder="Select output format",
            options=_make_format_options(default_output_format),
        )
        self.format_label = discord.ui.Label(text="Output Format", component=format_select)
        self.add_item(self.format_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Show visual feedback immediately
        await interaction.response.defer()
        await interaction.followup.send("🎨 **Generating edited image...** This may take a moment.", ephemeral=True)

        prompt = self.prompt_input.value

        # Get model, size, and quality from the select components
        model_select = self.model_label.component
        size_select = self.size_label.component
        quality_select = self.quality_label.component

        model = model_select.values[0] if model_select.values else "gpt-image-1.5"
        size = size_select.values[0] if size_select.values else "auto"
        quality = quality_select.values[0] if quality_select.values else "auto"
        format_select = self.format_label.component
        output_format = format_select.values[0] if format_select.values else "png"

        try:
            # Download the reference image with content type
            import aiohttp

            reference_images: list[tuple[str, bytes, str]] = []
            async with aiohttp.ClientSession() as session:
                async with session.get(self.reference_image_url) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
                        # Get content type from response or detect from URL
                        content_type = resp.content_type
                        if not content_type or content_type == "application/octet-stream":
                            # Try to detect from URL extension
                            url_lower = self.reference_image_url.lower()
                            if ".png" in url_lower:
                                content_type = "image/png"
                            elif ".webp" in url_lower:
                                content_type = "image/webp"
                            elif ".jpg" in url_lower or ".jpeg" in url_lower:
                                content_type = "image/jpeg"
                            else:
                                # Default to PNG
                                content_type = "image/png"

                        # Get extension from content type
                        ext = content_type.split("/")[-1]
                        if ext == "jpeg":
                            ext = "jpg"

                        reference_images.append((f"image.{ext}", image_bytes, content_type))

            if not reference_images:
                await interaction.followup.send("Failed to fetch the image for editing.", ephemeral=True)
                return

            await self.cog.generate_image(
                interaction=interaction,
                prompt=prompt,
                model=model,
                reference_images=reference_images,
                size=size,
                quality=quality,
                output_format=output_format,
            )
        except Exception as e:
            log.exception("Error editing image", exc_info=e)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


class EditImageButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ImGen:edit",
):
    """Dynamic button for editing an image by fetching the message attachment."""

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id="ImGen:edit",
                emoji="✏️",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: Red = interaction.client
        cog: t.Optional["ImGen"] = bot.get_cog("ImGen")
        if not cog:
            await interaction.response.send_message("ImGen cog is not loaded.", ephemeral=True)
            return

        # Check if user can generate
        conf = cog.db.get_conf(interaction.guild)
        can_gen, reason = conf.can_generate(interaction.user)
        if not can_gen:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        ok, reason, allowed_models, allowed_sizes, allowed_qualities, _access = cog._get_user_option_limits(
            conf, interaction.user
        )
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        default_model = conf.default_model if conf.default_model in allowed_models else allowed_models[0]
        default_size = conf.default_size if conf.default_size in allowed_sizes else allowed_sizes[0]
        default_quality = conf.default_quality if conf.default_quality in allowed_qualities else allowed_qualities[0]

        # Get the image URL from the message embed
        message = interaction.message
        if not message or not message.embeds:
            await interaction.response.send_message("Could not find the image to edit.", ephemeral=True)
            return

        embed = message.embeds[0]
        image_url = embed.image.url if embed.image else None

        if not image_url:
            await interaction.response.send_message("Could not find the image to edit.", ephemeral=True)
            return

        # Pass config defaults to the modal
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


def create_image_embed(
    prompt: str,
    model: str,
    size: str,
    quality: str,
    author: discord.User | discord.Member,
    title: str = "🎨 Generated Image",
) -> discord.Embed:
    """Create an embed displaying the generated image with its settings."""
    # Truncate prompt if too long for embed description
    display_prompt = prompt if len(prompt) <= 4000 else prompt[:3997] + "..."

    embed = discord.Embed(
        title=title,
        description=f"**Prompt:** {display_prompt}",
        color=discord.Color.purple(),
        timestamp=datetime.now(tz=timezone.utc),
    )

    # Add settings as fields
    embed.add_field(name="Model", value=model, inline=True)
    embed.add_field(name="Size", value=size, inline=True)
    embed.add_field(name="Quality", value=quality, inline=True)

    embed.set_footer(text=f"Requested by {author.display_name}", icon_url=author.display_avatar.url)

    return embed


class RoleAccessModal(discord.ui.Modal):
    """Modal for adding or updating role-based access."""

    def __init__(self, view: "AccessConfigView"):
        super().__init__(title="Add or Update Role Access", timeout=300)
        self.view = view

        role_select = discord.ui.RoleSelect(placeholder="Select role", min_values=1, max_values=1)
        self.role_label = discord.ui.Label(text="Role", component=role_select)
        self.add_item(self.role_label)

        self.model_values = list(VALID_MODELS)
        model_options = [discord.SelectOption(label="All models", value="__all__")]
        model_options.extend(
            [discord.SelectOption(label=MODEL_LABELS.get(value, value), value=value) for value in self.model_values]
        )
        model_select = discord.ui.Select(
            placeholder="Allowed models (leave empty for all)",
            options=model_options,
            min_values=1,
            max_values=len(model_options),
        )
        self.model_label = discord.ui.Label(text="Models", component=model_select)
        self.add_item(self.model_label)

        size_values = [value for value in VALID_SIZES if value != "auto"]
        self.size_values = size_values
        size_options = [discord.SelectOption(label="All sizes (auto allowed)", value="__all__")]
        size_options.extend(
            [discord.SelectOption(label=SIZE_LABELS.get(value, value), value=value) for value in size_values]
        )
        size_select = discord.ui.Select(
            placeholder="Allowed sizes (leave empty for all)",
            options=size_options,
            min_values=1,
            max_values=len(size_options),
        )
        self.size_label = discord.ui.Label(text="Sizes", component=size_select)
        self.add_item(self.size_label)

        quality_values = [value for value in VALID_QUALITIES if value != "auto"]
        self.quality_values = quality_values
        quality_options = [discord.SelectOption(label="All qualities (auto allowed)", value="__all__")]
        quality_options.extend(
            [discord.SelectOption(label=QUALITY_LABELS.get(value, value), value=value) for value in quality_values]
        )
        quality_select = discord.ui.Select(
            placeholder="Allowed qualities (leave empty for all)",
            options=quality_options,
            min_values=1,
            max_values=len(quality_options),
        )
        self.quality_label = discord.ui.Label(text="Qualities", component=quality_select)
        self.add_item(self.quality_label)

        self.cooldown_input = discord.ui.TextInput(
            label="Cooldown (seconds)",
            placeholder="60",
            default="60",
            required=True,
            min_length=1,
            max_length=6,
        )
        self.add_item(self.cooldown_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        role_select = self.role_label.component
        model_select = self.model_label.component
        size_select = self.size_label.component
        quality_select = self.quality_label.component

        role_value = role_select.values[0] if role_select.values else None
        if role_value is None:
            await interaction.response.send_message("You must select a role.", ephemeral=True)
            return
        if isinstance(role_value, discord.Role):
            role = role_value
            role_id = role.id
        else:
            try:
                role_id = int(role_value)
            except ValueError:
                await interaction.response.send_message("Invalid role selection.", ephemeral=True)
                return
            role = interaction.guild.get_role(role_id)

        try:
            cooldown = int(self.cooldown_input.value.strip())
        except ValueError:
            await interaction.response.send_message("Cooldown must be a number.", ephemeral=True)
            return

        if cooldown < 0:
            await interaction.response.send_message("Cooldown must be 0 or greater.", ephemeral=True)
            return

        conf = self.view.conf

        def normalize(values: list[str], all_values: list[str]) -> list[str]:
            if "__all__" in values:
                return []
            if set(values) == set(all_values):
                return []
            return values

        conf.role_cooldowns[role_id] = RoleCooldown(
            role_id=role_id,
            cooldown_seconds=cooldown,
            allowed_models=normalize(list(model_select.values), self.model_values),
            allowed_sizes=normalize(list(size_select.values), self.size_values),
            allowed_qualities=normalize(list(quality_select.values), self.quality_values),
        )
        await self.view.cog.save()

        self.view.refresh()
        await interaction.response.edit_message(view=self.view)
        role_mention = role.mention if role else f"<@&{role_id}>"
        await interaction.followup.send(
            f"✅ Updated access for {role_mention}.",
            ephemeral=True,
        )


class RemoveRoleAccessModal(discord.ui.Modal):
    """Modal for removing role-based access."""

    def __init__(self, view: "AccessConfigView"):
        super().__init__(title="Remove Role Access", timeout=300)
        self.view = view

        role_select = discord.ui.RoleSelect(placeholder="Select role", min_values=1, max_values=1)
        self.role_label = discord.ui.Label(text="Role", component=role_select)
        self.add_item(self.role_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        role_select = self.role_label.component
        role_value = role_select.values[0] if role_select.values else None
        if role_value is None:
            await interaction.response.send_message("You must select a role.", ephemeral=True)
            return
        if isinstance(role_value, discord.Role):
            role = role_value
            role_id = role.id
        else:
            try:
                role_id = int(role_value)
            except ValueError:
                await interaction.response.send_message("Invalid role selection.", ephemeral=True)
                return
            role = interaction.guild.get_role(role_id)

        conf = self.view.conf
        if role_id not in conf.role_cooldowns:
            await interaction.response.send_message("That role is not configured.", ephemeral=True)
            return

        del conf.role_cooldowns[role_id]
        await self.view.cog.save()

        self.view.refresh()
        await interaction.response.edit_message(view=self.view)
        role_mention = role.mention if role else f"<@&{role_id}>"
        await interaction.followup.send(
            f"✅ Removed access for {role_mention}.",
            ephemeral=True,
        )


class AccessConfigView(discord.ui.LayoutView):
    row = discord.ui.ActionRow()

    def __init__(self, cog: "ImGen", guild: discord.Guild):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.conf = cog.db.get_conf(guild)

        header = discord.ui.TextDisplay("# ImGen Role Access")
        self.access_text = discord.ui.TextDisplay(self._build_access_text())
        help_text = discord.ui.TextDisplay("-# Use the buttons below to add, update, or remove role access rules.")

        container = discord.ui.Container(
            header,
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            self.access_text,
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            help_text,
            accent_color=discord.Color.blurple(),
        )
        self.add_item(container)

        self.remove_item(self.row)
        self.add_item(self.row)

    def _build_access_text(self) -> str:
        if not self.conf.role_cooldowns:
            return "## Role Access\n-# Open access. Add a role to restrict usage."

        lines = ["## Role Access"]
        roles: list[tuple[discord.Role, RoleCooldown]] = []
        for role_id, rc in self.conf.role_cooldowns.items():
            role = self.guild.get_role(role_id)
            if role:
                roles.append((role, rc))

        if not roles:
            return "## Role Access\n-# Roles configured but not found in this guild."

        roles.sort(key=lambda item: item[0].position, reverse=True)
        for role, rc in roles:
            cooldown_txt = "No cooldown" if rc.cooldown_seconds <= 0 else f"{rc.cooldown_seconds}s cooldown"
            models_txt = (
                "All models"
                if not rc.allowed_models
                else ", ".join(MODEL_LABELS.get(value, value) for value in rc.allowed_models)
            )
            sizes_txt = (
                "All sizes (auto allowed)"
                if not rc.allowed_sizes
                else ", ".join(SIZE_LABELS.get(value, value) for value in rc.allowed_sizes)
            )
            qualities_txt = (
                "All qualities (auto allowed)"
                if not rc.allowed_qualities
                else ", ".join(QUALITY_LABELS.get(value, value) for value in rc.allowed_qualities)
            )

            lines.append(
                f"- {role.mention}: {cooldown_txt}\n"
                f"  - Models: {models_txt}\n"
                f"  - Sizes: {sizes_txt}\n"
                f"  - Qualities: {qualities_txt}"
            )

        return "\n".join(lines)

    def refresh(self) -> None:
        self.access_text.content = self._build_access_text()

    @row.button(label="Add/Update", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(RoleAccessModal(self))

    @row.button(label="Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(RemoveRoleAccessModal(self))

    @row.button(label="Close", style=discord.ButtonStyle.secondary, emoji="✅")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(view=self)
        await interaction.delete_original_response()


class SetApiKeyModal(discord.ui.Modal):
    """Modal for setting the OpenAI API key."""

    def __init__(self, cog: "ImGen"):
        super().__init__(title="Set OpenAI API Key", timeout=300)
        self.cog = cog

        self.api_key_input = discord.ui.TextInput(
            label="OpenAI API Key",
            placeholder="sk-...",
            style=discord.TextStyle.short,
            required=True,
            min_length=20,
            max_length=200,
        )
        self.add_item(self.api_key_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        conf = self.cog.db.get_conf(interaction.guild)
        conf.api_key = self.api_key_input.value.strip()
        await self.cog.save()

        await interaction.followup.send("✅ OpenAI API key has been set for this server.", ephemeral=True)


class SetApiKeyButton(discord.ui.Button):
    """Button that opens the API key modal."""

    def __init__(self, cog: "ImGen"):
        super().__init__(
            label="Set API Key",
            style=discord.ButtonStyle.primary,
            emoji="🔑",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        modal = SetApiKeyModal(self.cog)
        await interaction.response.send_modal(modal)


class SetApiKeyView(discord.ui.View):
    """View for setting the API key."""

    def __init__(self, cog: "ImGen"):
        super().__init__(timeout=300)
        self.add_item(SetApiKeyButton(cog))
