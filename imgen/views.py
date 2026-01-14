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


class EditImageModal(discord.ui.Modal):
    """Modal for editing an image with a new prompt and settings dropdowns."""

    prompt_input = discord.ui.TextInput(
        label="Edit Prompt",
        placeholder="Describe how you want to modify the image...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    size_label = discord.ui.Label(
        text="Size",
        component=discord.ui.Select(
            placeholder="Select image size",
            options=[
                discord.SelectOption(label="Auto", value="auto", default=True),
                discord.SelectOption(label="1024x1024 (Square)", value="1024x1024"),
                discord.SelectOption(label="1536x1024 (Landscape)", value="1536x1024"),
                discord.SelectOption(label="1024x1536 (Portrait)", value="1024x1536"),
            ],
        ),
    )

    quality_label = discord.ui.Label(
        text="Quality",
        component=discord.ui.Select(
            placeholder="Select image quality",
            options=[
                discord.SelectOption(label="Auto", value="auto", default=True),
                discord.SelectOption(label="Low", value="low"),
                discord.SelectOption(label="Medium", value="medium"),
                discord.SelectOption(label="High", value="high"),
            ],
        ),
    )

    def __init__(
        self,
        cog: "ImGen",
        response_id: str | None = None,
        reference_image_url: str | None = None,
    ):
        super().__init__(title="Edit Image", timeout=300)
        self.cog = cog
        self.response_id = response_id
        self.reference_image_url = reference_image_url

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Show visual feedback immediately
        await interaction.response.defer()
        await interaction.followup.send("🎨 **Generating edited image...** This may take a moment.", ephemeral=True)

        prompt = self.prompt_input.value

        # Get size and quality from the select components
        size_select = self.size_label.component
        quality_select = self.quality_label.component

        size = size_select.values[0] if size_select.values else "auto"
        quality = quality_select.values[0] if quality_select.values else "auto"

        try:
            # If we have a reference image URL (from context menu), download it
            reference_images = None
            if self.reference_image_url:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.get(self.reference_image_url) as resp:
                        if resp.status == 200:
                            reference_images = [await resp.read()]

            await self.cog.generate_image(
                interaction=interaction,
                prompt=prompt,
                previous_response_id=self.response_id,
                reference_images=reference_images,
                size=size,
                quality=quality,
            )
        except Exception as e:
            log.exception("Error editing image", exc_info=e)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


class EditImageButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ImGen:edit:(?P<response_id>[a-zA-Z0-9_-]+)",
):
    """Dynamic button for editing an image using previous response ID."""

    def __init__(self, response_id: str = "") -> None:
        self.response_id = response_id
        super().__init__(
            discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id=f"ImGen:edit:{response_id}",
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
        return cls(match["response_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: Red = interaction.client
        cog: t.Optional["ImGen"] = bot.get_cog("ImGen")
        if not cog:
            await interaction.response.send_message("ImGen cog is not loaded.", ephemeral=True)
            return

        # Check if user can generate
        if interaction.guild:
            conf = cog.db.get_conf(interaction.guild)
            can_gen, reason = conf.can_generate(interaction.user)
            if not can_gen:
                await interaction.response.send_message(reason, ephemeral=True)
                return

        modal = EditImageModal(cog, self.response_id)
        await interaction.response.send_modal(modal)


def create_image_view(response_id: str) -> discord.ui.View:
    """Create a view with the edit button."""
    view = discord.ui.View(timeout=None)
    view.add_item(EditImageButton(response_id).item)
    return view


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
