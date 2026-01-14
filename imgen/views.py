import logging
import re
import typing as t
from datetime import datetime, timezone

import discord
from redbot.core.bot import Red

if t.TYPE_CHECKING:
    from .main import ImGen

log = logging.getLogger("red.vrt.imgen.views")

# Options for dropdowns
SIZE_OPTIONS = [
    discord.SelectOption(label="Auto", value="auto", default=True),
    discord.SelectOption(label="1024x1024 (Square)", value="1024x1024"),
    discord.SelectOption(label="1536x1024 (Landscape)", value="1536x1024"),
    discord.SelectOption(label="1024x1536 (Portrait)", value="1024x1536"),
]

QUALITY_OPTIONS = [
    discord.SelectOption(label="Auto", value="auto", default=True),
    discord.SelectOption(label="Low", value="low"),
    discord.SelectOption(label="Medium", value="medium"),
    discord.SelectOption(label="High", value="high"),
]

MODEL_OPTIONS = [
    discord.SelectOption(label="GPT Image 1.5", value="gpt-image-1.5", default=True),
    discord.SelectOption(label="GPT Image 1 Mini", value="gpt-image-1-mini"),
]


def _make_model_options(default: str = "gpt-image-1.5") -> list[discord.SelectOption]:
    """Create model options with the specified default."""
    models = [
        ("GPT Image 1.5", "gpt-image-1.5"),
        ("GPT Image 1 Mini", "gpt-image-1-mini"),
    ]
    return [discord.SelectOption(label=label, value=value, default=(value == default)) for label, value in models]


def _make_size_options(default: str = "auto") -> list[discord.SelectOption]:
    """Create size options with the specified default."""
    sizes = [
        ("Auto", "auto"),
        ("1024x1024 (Square)", "1024x1024"),
        ("1536x1024 (Landscape)", "1536x1024"),
        ("1024x1536 (Portrait)", "1024x1536"),
    ]
    return [discord.SelectOption(label=label, value=value, default=(value == default)) for label, value in sizes]


def _make_quality_options(default: str = "auto") -> list[discord.SelectOption]:
    """Create quality options with the specified default."""
    qualities = [
        ("Auto", "auto"),
        ("Low", "low"),
        ("Medium", "medium"),
        ("High", "high"),
    ]
    return [discord.SelectOption(label=label, value=value, default=(value == default)) for label, value in qualities]


class EditImageModal(discord.ui.Modal):
    """Modal for editing an image with a new prompt and settings dropdowns."""

    def __init__(
        self,
        cog: "ImGen",
        reference_image_url: str,
        default_model: str = "gpt-image-1.5",
        default_size: str = "auto",
        default_quality: str = "auto",
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
            options=_make_model_options(default_model),
        )
        self.model_label = discord.ui.Label(text="Model", component=model_select)
        self.add_item(self.model_label)

        size_select = discord.ui.Select(
            placeholder="Select image size",
            options=_make_size_options(default_size),
        )
        self.size_label = discord.ui.Label(text="Size", component=size_select)
        self.add_item(self.size_label)

        quality_select = discord.ui.Select(
            placeholder="Select image quality",
            options=_make_quality_options(default_quality),
        )
        self.quality_label = discord.ui.Label(text="Quality", component=quality_select)
        self.add_item(self.quality_label)

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
            default_model=conf.default_model,
            default_size=conf.default_size,
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
