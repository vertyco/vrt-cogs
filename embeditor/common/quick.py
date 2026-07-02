import logging

import discord

log = logging.getLogger("red.vrt.embeditor.quick")

MAX_INPUTS = 5


class QuickEditModal(discord.ui.Modal):
    """Dynamic modal showing inputs only for parts the message already has."""

    def __init__(self, message: discord.Message):
        super().__init__(title="Quick Edit", timeout=900)
        self.message = message
        self.inputs: dict[str, discord.ui.TextInput] = {}

        if message.content:
            self.add_input(
                "content",
                "Message Content",
                message.content,
                discord.TextStyle.paragraph,
                2000,
            )
        if len(message.embeds) == 1:
            embed = message.embeds[0]
            candidates = [
                ("title", embed.title, 256, discord.TextStyle.short),
                ("description", embed.description, 4000, discord.TextStyle.paragraph),
                ("author name", embed.author.name, 256, discord.TextStyle.short),
                ("author icon url", embed.author.icon_url, None, discord.TextStyle.paragraph),
                ("footer text", embed.footer.text, 2048, discord.TextStyle.paragraph),
                ("footer icon url", embed.footer.icon_url, None, discord.TextStyle.paragraph),
                ("thumbnail", embed.thumbnail.url, None, discord.TextStyle.paragraph),
                ("image", embed.image.url, None, discord.TextStyle.paragraph),
            ]
            for key, current, max_length, style in candidates:
                current = str(current).strip() if current else None
                if not current:
                    continue
                if max_length and len(current) > max_length:
                    continue
                self.add_input(key, key.title(), current, style, max_length)

    def add_input(
        self,
        key: str,
        label: str,
        default: str,
        style: discord.TextStyle,
        max_length: int | None,
    ) -> None:
        if len(self.inputs) >= MAX_INPUTS:
            return
        field = discord.ui.TextInput(
            label=label,
            style=style,
            default=default,
            required=False,
            max_length=max_length,
        )
        self.add_item(field)
        self.inputs[key] = field

    def apply(self) -> tuple[bool, str | None, list[discord.Embed]]:
        """Build the new content/embeds from modal values. Returns (changed, content, embeds)."""
        changed = False
        content = self.message.content or None
        if "content" in self.inputs and self.inputs["content"].value != self.message.content:
            content = self.inputs["content"].value or None
            changed = True

        embeds = list(self.message.embeds)
        if len(embeds) == 1:
            embed = embeds[0]
            values = {k: v.value.strip() or None for k, v in self.inputs.items() if k != "content"}
            for key, new in values.items():
                match key:
                    case "title" if new != embed.title:
                        embed.title = new
                    case "description" if new != embed.description:
                        embed.description = new
                    case "author name" if new != embed.author.name:
                        embed.set_author(name=new, icon_url=embed.author.icon_url)
                    case "author icon url" if new != embed.author.icon_url:
                        embed.set_author(name=embed.author.name, icon_url=new)
                    case "footer text" if new != embed.footer.text:
                        embed.set_footer(text=new, icon_url=embed.footer.icon_url)
                    case "footer icon url" if new != embed.footer.icon_url:
                        embed.set_footer(text=embed.footer.text, icon_url=new)
                    case "thumbnail" if new != embed.thumbnail.url:
                        embed.set_thumbnail(url=new)
                    case "image" if new != embed.image.url:
                        embed.set_image(url=new)
                    case _:
                        continue
                changed = True
        return changed, content, embeds

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        changed, content, embeds = self.apply()
        if not changed:
            return await interaction.followup.send("No changes detected.", ephemeral=True)
        try:
            await self.message.edit(content=content, embeds=embeds)
        except discord.HTTPException as e:
            log.error(f"Quick edit failed for message {self.message.id}", exc_info=e)
            return await interaction.followup.send(f"Failed to edit message: {e}", ephemeral=True)
        await interaction.followup.send("Message edited.", ephemeral=True)
        log.info(f"{interaction.user} quick-edited message {self.message.id} in {interaction.guild}")

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error("QuickEditModal error", exc_info=error)
