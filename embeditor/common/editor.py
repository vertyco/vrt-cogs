import logging
from contextlib import suppress
from datetime import datetime, timezone

import discord
from dateutil import parser as dateparser
from discord.components import (
    ActionRow as ActionRowComponent,
    Container as ContainerComponent,
    MediaGalleryComponent,
    SeparatorComponent,
    TextDisplay as TextDisplayComponent,
)

log = logging.getLogger("red.vrt.embeditor.editor")

EDITOR_TIMEOUT = 900
MAX_ITEMS = 20
MAX_FIELDS = 25
YES = ("yes", "y", "true", "1")


def parse_colour(text: str) -> discord.Colour | None:
    """Parse a hex colour string like '#5865F2'. Empty string returns None."""
    text = text.strip().lstrip("#")
    if not text:
        return None
    return discord.Colour(int(text, 16))


def parse_timestamp(text: str) -> datetime | None:
    """Parse 'now', an ISO string, or a humanized date. Empty string returns None."""
    text = text.strip()
    if not text:
        return None
    if text.lower() == "now":
        return datetime.now(timezone.utc)
    try:
        return dateparser.parse(text)
    except (ValueError, OverflowError) as e:
        raise ValueError(f"`{text}` is not a recognized date/time.") from e


def parse_urls(text: str, limit: int) -> list[str]:
    """Parse newline separated URLs, validating each."""
    urls = [line.strip() for line in text.splitlines() if line.strip()]
    for url in urls:
        if "://" not in url:
            raise ValueError(f"`{url}` is not a valid URL.")
    return urls[:limit]


def parse_buttons(text: str) -> list[tuple[str, str]]:
    """Parse newline separated 'Label | URL' pairs."""
    buttons: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" not in line:
            raise ValueError(f"`{line}` must be formatted as `Label | URL`.")
        label, _, url = line.partition("|")
        label, url = label.strip(), url.strip()
        if not label or "://" not in url:
            raise ValueError(f"`{line}` must be formatted as `Label | URL` with a valid URL.")
        buttons.append((label[:80], url))
    return buttons[:5]


def item_label(item: dict) -> str:
    """Short human label for a container item, used in pickers."""
    match item["type"]:
        case "text":
            return f"Text: {item['text']}"
        case "media":
            return f"Media: {len(item['urls'])} item(s)"
        case "sep":
            divider = "divider" if item["divider"] else "invisible"
            spacing = "large" if item["large"] else "small"
            return f"Separator ({divider}, {spacing})"
        case "buttons":
            return f"Buttons: {', '.join(label for label, _ in item['buttons'])}"
        case _:
            return "Unknown"


class GenericModal(discord.ui.Modal):
    """Reusable modal that collects named text inputs and hands them to a callback."""

    def __init__(self, title: str, callback):
        super().__init__(title=title, timeout=600)
        self.callback_fn = callback
        self.inputs: dict[str, discord.ui.TextInput] = {}

    def add_input(
        self,
        key: str,
        label: str,
        default: str | None = None,
        style: discord.TextStyle = discord.TextStyle.short,
        max_length: int | None = None,
        placeholder: str | None = None,
    ) -> "GenericModal":
        field = discord.ui.TextInput(
            label=label,
            style=style,
            default=default,
            required=False,
            max_length=max_length,
            placeholder=placeholder,
        )
        self.add_item(field)
        self.inputs[key] = field
        return self

    async def on_submit(self, interaction: discord.Interaction):
        values = {k: v.value.strip() for k, v in self.inputs.items()}
        try:
            await self.callback_fn(interaction, values)
        except ValueError as e:
            log.warning(f"Invalid modal input: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Invalid input: {e}", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error("Editor modal error", exc_info=error)


class PickerView(discord.ui.View):
    """Ephemeral single-select used to pick an embed field or text block by index."""

    def __init__(self, session: "EditorSession", labels: list[str], on_pick):
        super().__init__(timeout=300)
        self.session = session
        self.on_pick = on_pick
        options = [
            discord.SelectOption(label=label[:100] or "(blank)", value=str(i)) for i, label in enumerate(labels[:25])
        ]
        self.select = discord.ui.Select(placeholder="Select one", options=options)
        self.select.callback = self.picked
        self.add_item(self.select)

    async def picked(self, interaction: discord.Interaction):
        self.stop()
        await self.on_pick(interaction, int(self.select.values[0]))


class EmbedEditorView(discord.ui.View):
    """Button menu attached to the preview message while in embed mode."""

    def __init__(self, session: "EditorSession"):
        super().__init__(timeout=EDITOR_TIMEOUT)
        self.session = session
        buttons = [
            ("Content", discord.ButtonStyle.primary, session.content_button, 0),
            ("Body", discord.ButtonStyle.primary, session.body_button, 0),
            ("Author", discord.ButtonStyle.secondary, session.author_button, 0),
            ("Footer", discord.ButtonStyle.secondary, session.footer_button, 0),
            ("Images", discord.ButtonStyle.secondary, session.images_button, 0),
            ("Add Field", discord.ButtonStyle.success, session.add_field_button, 1),
            ("Edit Field", discord.ButtonStyle.secondary, session.edit_field_button, 1),
            ("Remove Field", discord.ButtonStyle.danger, session.remove_field_button, 1),
        ]
        toggle = "Remove Embed" if session.embed else "Add Embed"
        buttons.append((toggle, discord.ButtonStyle.secondary, session.toggle_embed_button, 2))
        if not session.locked_v2:
            buttons.append(("To Container", discord.ButtonStyle.secondary, session.to_container_button, 2))
        buttons.append(("Save", discord.ButtonStyle.success, session.save_button, 3))
        buttons.append(("Cancel", discord.ButtonStyle.danger, session.cancel_button, 3))
        for label, style, callback, row in buttons:
            button = discord.ui.Button(label=label, style=style, row=row)
            button.callback = callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.session.guard(interaction)

    async def on_timeout(self):
        await self.session.expire()


class ContainerEditorView(discord.ui.LayoutView):
    """Preview + button menu rendered as a components v2 layout while in container mode."""

    def __init__(self, session: "EditorSession"):
        super().__init__(timeout=EDITOR_TIMEOUT)
        self.session = session
        self.add_item(session.build_container())
        row1 = discord.ui.ActionRow()
        row2 = discord.ui.ActionRow()
        row3 = discord.ui.ActionRow()
        buttons = [
            ("Add Text", discord.ButtonStyle.success, session.add_text_button, row1),
            ("Add Media", discord.ButtonStyle.success, session.add_media_button, row1),
            ("Add Separator", discord.ButtonStyle.success, session.add_separator_button, row1),
            ("Add Buttons", discord.ButtonStyle.success, session.add_buttons_button, row1),
            ("Edit Item", discord.ButtonStyle.primary, session.edit_item_button, row2),
            ("Remove Item", discord.ButtonStyle.danger, session.remove_item_button, row2),
            ("Accent Color", discord.ButtonStyle.secondary, session.accent_button, row2),
            ("Save", discord.ButtonStyle.success, session.save_button, row3),
            ("Cancel", discord.ButtonStyle.danger, session.cancel_button, row3),
        ]
        if not session.locked_v2:
            buttons.insert(7, ("To Embed", discord.ButtonStyle.secondary, session.to_embed_button, row3))
        for label, style, callback, row in buttons:
            button = discord.ui.Button(label=label, style=style)
            button.callback = callback
            row.add_item(button)
        self.add_item(row1)
        self.add_item(row2)
        self.add_item(row3)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.session.guard(interaction)

    async def on_timeout(self):
        await self.session.expire()


class SavedLayout(discord.ui.LayoutView):
    """Static layout applied to the target message when saving in container mode."""

    def __init__(self, container: discord.ui.Container):
        super().__init__(timeout=1)
        self.add_item(container)


class EditorSession:
    """Holds the working copy of a message and drives the full editor UI."""

    def __init__(self, interaction: discord.Interaction, message: discord.Message):
        self.user = interaction.user
        self.channel = message.channel
        self.target = message
        self.locked_v2 = message.flags.components_v2
        self.mode = "container" if self.locked_v2 else "embed"
        self.rendered_mode = self.mode
        self.content: str = message.content or ""
        self.embed: discord.Embed | None = message.embeds[0] if message.embeds else None
        self.items: list[dict] = []
        self.accent: discord.Colour | None = None
        self.editor_msg: discord.Message | None = None
        self.done = False
        if self.locked_v2:
            self.parse_components(message)
        if self.mode == "container" and not self.items:
            self.items = [{"type": "text", "text": "*empty*"}]

    def parse_component(self, component) -> None:
        if isinstance(component, TextDisplayComponent):
            self.items.append({"type": "text", "text": component.content})
        elif isinstance(component, MediaGalleryComponent):
            urls = [item.media.url for item in component.items if item.media]
            if urls:
                self.items.append({"type": "media", "urls": urls})
        elif isinstance(component, SeparatorComponent):
            self.items.append(
                {
                    "type": "sep",
                    "divider": component.visible,
                    "large": component.spacing == discord.SeparatorSpacing.large,
                }
            )
        elif isinstance(component, ActionRowComponent):
            buttons = [
                (child.label or "Link", child.url) for child in component.children if getattr(child, "url", None)
            ]
            if buttons:
                self.items.append({"type": "buttons", "buttons": buttons})

    def parse_components(self, message: discord.Message) -> None:
        for component in message.components:
            if isinstance(component, ContainerComponent):
                self.accent = component.accent_colour
                for child in component.children:
                    self.parse_component(child)
            else:
                self.parse_component(component)

    async def start(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        self.editor_msg = await self.send_editor()
        await interaction.followup.send(
            "Editor opened below the target message. Changes only apply when you hit Save.", ephemeral=True
        )

    async def guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user.id:
            return True
        with suppress(discord.HTTPException):
            await interaction.response.send_message("This editor belongs to someone else.", ephemeral=True)
        return False

    def preview_content(self) -> str | None:
        if self.content:
            return self.content
        return None if self.embed else "-# *empty message*"

    def build_item(self, item: dict) -> discord.ui.Item:
        match item["type"]:
            case "text":
                return discord.ui.TextDisplay(item["text"])
            case "media":
                gallery_items = [discord.MediaGalleryItem(url) for url in item["urls"]]
                return discord.ui.MediaGallery(*gallery_items)
            case "sep":
                spacing = discord.SeparatorSpacing.large if item["large"] else discord.SeparatorSpacing.small
                return discord.ui.Separator(visible=item["divider"], spacing=spacing)
            case "buttons":
                row = discord.ui.ActionRow()
                for label, url in item["buttons"]:
                    row.add_item(discord.ui.Button(label=label, url=url))
                return row
            case _:
                raise ValueError(f"Unknown container item type: {item['type']}")

    def build_container(self) -> discord.ui.Container:
        children = [self.build_item(item) for item in self.items]
        return discord.ui.Container(*children, accent_colour=self.accent)

    async def send_editor(self) -> discord.Message:
        if self.mode == "embed":
            return await self.channel.send(content=self.preview_content(), embed=self.embed, view=EmbedEditorView(self))
        return await self.channel.send(view=ContainerEditorView(self))

    async def refresh(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer()
        if self.done or self.editor_msg is None:
            return
        if self.mode != self.rendered_mode:
            old = self.editor_msg
            self.editor_msg = await self.send_editor()
            self.rendered_mode = self.mode
            with suppress(discord.HTTPException):
                await old.delete()
            return
        try:
            if self.mode == "embed":
                await self.editor_msg.edit(content=self.preview_content(), embed=self.embed, view=EmbedEditorView(self))
            else:
                await self.editor_msg.edit(view=ContainerEditorView(self))
        except discord.HTTPException as e:
            log.error("Failed to refresh editor preview", exc_info=e)
            with suppress(discord.HTTPException):
                await interaction.followup.send(f"Failed to update preview: {e}", ephemeral=True)

    def ensure_embed(self) -> discord.Embed:
        if self.embed is None:
            self.embed = discord.Embed()
        return self.embed

    # ------------------------- Embed mode buttons -------------------------

    async def content_button(self, interaction: discord.Interaction):
        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            self.content = values["content"]
            await self.refresh(modal_interaction)

        modal = GenericModal("Message Content", submit)
        modal.add_input("content", "Content", self.content or None, discord.TextStyle.paragraph, 2000)
        await interaction.response.send_modal(modal)

    async def body_button(self, interaction: discord.Interaction):
        embed = self.ensure_embed()

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            timestamp = parse_timestamp(values["timestamp"])
            target = self.ensure_embed()
            target.title = values["title"] or None
            target.description = values["description"] or None
            target.url = values["url"] or None
            target.colour = parse_colour(values["colour"])
            target.timestamp = timestamp
            await self.refresh(modal_interaction)

        colour = f"#{embed.colour.value:06X}" if embed.colour else None
        timestamp = embed.timestamp.isoformat() if embed.timestamp else None
        modal = GenericModal("Embed Body", submit)
        modal.add_input("title", "Title", embed.title, max_length=256)
        modal.add_input("description", "Description", embed.description, discord.TextStyle.paragraph, 4000)
        modal.add_input("url", "Title URL", embed.url)
        modal.add_input("colour", "Color (hex)", colour, placeholder="#5865F2")
        modal.add_input("timestamp", "Timestamp (now / ISO / date)", timestamp, placeholder="now")
        await interaction.response.send_modal(modal)

    async def author_button(self, interaction: discord.Interaction):
        embed = self.ensure_embed()

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            target = self.ensure_embed()
            if values["name"]:
                target.set_author(name=values["name"], icon_url=values["icon"] or None, url=values["url"] or None)
            else:
                target.remove_author()
            await self.refresh(modal_interaction)

        modal = GenericModal("Embed Author", submit)
        modal.add_input("name", "Author Name", embed.author.name, max_length=256)
        modal.add_input("icon", "Author Icon URL", embed.author.icon_url, discord.TextStyle.paragraph)
        modal.add_input("url", "Author URL", embed.author.url, discord.TextStyle.paragraph)
        await interaction.response.send_modal(modal)

    async def footer_button(self, interaction: discord.Interaction):
        embed = self.ensure_embed()

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            target = self.ensure_embed()
            if values["text"] or values["icon"]:
                target.set_footer(text=values["text"] or None, icon_url=values["icon"] or None)
            else:
                target.remove_footer()
            await self.refresh(modal_interaction)

        modal = GenericModal("Embed Footer", submit)
        modal.add_input("text", "Footer Text", embed.footer.text, discord.TextStyle.paragraph, 2048)
        modal.add_input("icon", "Footer Icon URL", embed.footer.icon_url, discord.TextStyle.paragraph)
        await interaction.response.send_modal(modal)

    async def images_button(self, interaction: discord.Interaction):
        embed = self.ensure_embed()

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            target = self.ensure_embed()
            target.set_thumbnail(url=values["thumbnail"] or None)
            target.set_image(url=values["image"] or None)
            await self.refresh(modal_interaction)

        modal = GenericModal("Embed Images", submit)
        modal.add_input("thumbnail", "Thumbnail URL", embed.thumbnail.url, discord.TextStyle.paragraph)
        modal.add_input("image", "Image URL", embed.image.url, discord.TextStyle.paragraph)
        await interaction.response.send_modal(modal)

    def field_modal(self, title: str, callback, name: str | None = None, value: str | None = None) -> GenericModal:
        modal = GenericModal(title, callback)
        modal.add_input("name", "Field Name", name, max_length=256)
        modal.add_input("value", "Field Value", value, discord.TextStyle.paragraph, 1024)
        modal.add_input("inline", "Inline? (yes/no)", None, placeholder="yes")
        return modal

    async def add_field_button(self, interaction: discord.Interaction):
        embed = self.ensure_embed()
        if len(embed.fields) >= MAX_FIELDS:
            return await interaction.response.send_message("Embeds can only have 25 fields.", ephemeral=True)

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            if values["name"] and values["value"]:
                inline = values["inline"].lower() not in ("no", "n", "false", "0")
                self.ensure_embed().add_field(name=values["name"], value=values["value"], inline=inline)
            await self.refresh(modal_interaction)

        await interaction.response.send_modal(self.field_modal("Add Field", submit))

    async def edit_field_button(self, interaction: discord.Interaction):
        if not self.embed or not self.embed.fields:
            return await interaction.response.send_message("There are no fields to edit.", ephemeral=True)

        async def picked(pick_interaction: discord.Interaction, index: int):
            field = self.ensure_embed().fields[index]

            async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
                inline = values["inline"].lower() not in ("no", "n", "false", "0")
                self.ensure_embed().set_field_at(index, name=values["name"], value=values["value"], inline=inline)
                await self.refresh(modal_interaction)

            modal = self.field_modal(f"Edit Field {index + 1}", submit, field.name, field.value)
            await pick_interaction.response.send_modal(modal)

        labels = [f"{i + 1}. {field.name}" for i, field in enumerate(self.embed.fields)]
        view = PickerView(self, labels, picked)
        await interaction.response.send_message("Pick a field to edit:", view=view, ephemeral=True)

    async def remove_field_button(self, interaction: discord.Interaction):
        if not self.embed or not self.embed.fields:
            return await interaction.response.send_message("There are no fields to remove.", ephemeral=True)

        async def picked(pick_interaction: discord.Interaction, index: int):
            self.ensure_embed().remove_field(index)
            await self.refresh(pick_interaction)

        labels = [f"{i + 1}. {field.name}" for i, field in enumerate(self.embed.fields)]
        view = PickerView(self, labels, picked)
        await interaction.response.send_message("Pick a field to remove:", view=view, ephemeral=True)

    async def toggle_embed_button(self, interaction: discord.Interaction):
        if self.embed:
            self.embed = None
        else:
            self.embed = discord.Embed(description="*empty embed*")
        await self.refresh(interaction)

    # ------------------------- Container mode buttons -------------------------

    def room_error(self) -> str | None:
        if len(self.items) >= MAX_ITEMS:
            return f"Containers are capped at {MAX_ITEMS} items here."
        return None

    def text_modal(self, title: str, callback, default: str | None = None) -> GenericModal:
        modal = GenericModal(title, callback)
        modal.add_input("text", "Text (markdown supported)", default, discord.TextStyle.paragraph, 4000)
        return modal

    def media_modal(self, title: str, callback, default: str | None = None) -> GenericModal:
        modal = GenericModal(title, callback)
        modal.add_input(
            "urls",
            "Media URLs (one per line, max 10)",
            default,
            discord.TextStyle.paragraph,
            placeholder="https://example.com/image.png",
        )
        return modal

    def separator_modal(self, title: str, callback, item: dict | None = None) -> GenericModal:
        modal = GenericModal(title, callback)
        divider = "yes" if item is None or item["divider"] else "no"
        large = "yes" if item and item["large"] else "no"
        modal.add_input("divider", "Show divider line? (yes/no)", divider, max_length=5)
        modal.add_input("large", "Large spacing? (yes/no)", large, max_length=5)
        return modal

    def buttons_modal(self, title: str, callback, item: dict | None = None) -> GenericModal:
        default = "\n".join(f"{label} | {url}" for label, url in item["buttons"]) if item else None
        modal = GenericModal(title, callback)
        modal.add_input(
            "buttons",
            "Buttons (Label | URL per line, max 5)",
            default,
            discord.TextStyle.paragraph,
            placeholder="Website | https://example.com",
        )
        return modal

    async def add_text_button(self, interaction: discord.Interaction):
        if error := self.room_error():
            return await interaction.response.send_message(error, ephemeral=True)

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            if values["text"]:
                self.items.append({"type": "text", "text": values["text"]})
            await self.refresh(modal_interaction)

        await interaction.response.send_modal(self.text_modal("Add Text Block", submit))

    async def add_media_button(self, interaction: discord.Interaction):
        if error := self.room_error():
            return await interaction.response.send_message(error, ephemeral=True)

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            urls = parse_urls(values["urls"], 10)
            if urls:
                self.items.append({"type": "media", "urls": urls})
            await self.refresh(modal_interaction)

        await interaction.response.send_modal(self.media_modal("Add Media Gallery", submit))

    async def add_separator_button(self, interaction: discord.Interaction):
        if error := self.room_error():
            return await interaction.response.send_message(error, ephemeral=True)

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            self.items.append(
                {
                    "type": "sep",
                    "divider": values["divider"].lower() in YES,
                    "large": values["large"].lower() in YES,
                }
            )
            await self.refresh(modal_interaction)

        await interaction.response.send_modal(self.separator_modal("Add Separator", submit))

    async def add_buttons_button(self, interaction: discord.Interaction):
        if error := self.room_error():
            return await interaction.response.send_message(error, ephemeral=True)

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            buttons = parse_buttons(values["buttons"])
            if buttons:
                self.items.append({"type": "buttons", "buttons": buttons})
            await self.refresh(modal_interaction)

        await interaction.response.send_modal(self.buttons_modal("Add Link Buttons", submit))

    async def edit_item_modal(self, interaction: discord.Interaction, index: int):
        item = self.items[index]

        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            match item["type"]:
                case "text":
                    item["text"] = values["text"] or "*empty*"
                case "media":
                    urls = parse_urls(values["urls"], 10)
                    if not urls:
                        raise ValueError("A media gallery needs at least one URL.")
                    item["urls"] = urls
                case "sep":
                    item["divider"] = values["divider"].lower() in YES
                    item["large"] = values["large"].lower() in YES
                case "buttons":
                    buttons = parse_buttons(values["buttons"])
                    if not buttons:
                        raise ValueError("At least one `Label | URL` line is required.")
                    item["buttons"] = buttons
            await self.refresh(modal_interaction)

        title = f"Edit Item {index + 1}"
        match item["type"]:
            case "text":
                modal = self.text_modal(title, submit, item["text"])
            case "media":
                modal = self.media_modal(title, submit, "\n".join(item["urls"]))
            case "sep":
                modal = self.separator_modal(title, submit, item)
            case _:
                modal = self.buttons_modal(title, submit, item)
        await interaction.response.send_modal(modal)

    async def edit_item_button(self, interaction: discord.Interaction):
        if len(self.items) == 1:
            return await self.edit_item_modal(interaction, 0)

        async def picked(pick_interaction: discord.Interaction, index: int):
            await self.edit_item_modal(pick_interaction, index)

        labels = [f"{i + 1}. {item_label(item)}" for i, item in enumerate(self.items)]
        view = PickerView(self, labels, picked)
        await interaction.response.send_message("Pick an item to edit:", view=view, ephemeral=True)

    async def remove_item_button(self, interaction: discord.Interaction):
        if len(self.items) <= 1:
            return await interaction.response.send_message(
                "Containers need at least one item. Edit it instead.", ephemeral=True
            )

        async def picked(pick_interaction: discord.Interaction, index: int):
            self.items.pop(index)
            await self.refresh(pick_interaction)

        labels = [f"{i + 1}. {item_label(item)}" for i, item in enumerate(self.items)]
        view = PickerView(self, labels, picked)
        await interaction.response.send_message("Pick an item to remove:", view=view, ephemeral=True)

    async def accent_button(self, interaction: discord.Interaction):
        async def submit(modal_interaction: discord.Interaction, values: dict[str, str]):
            self.accent = parse_colour(values["colour"])
            await self.refresh(modal_interaction)

        colour = f"#{self.accent.value:06X}" if self.accent else None
        modal = GenericModal("Accent Color", submit)
        modal.add_input("colour", "Color (hex, blank for none)", colour, placeholder="#5865F2")
        await interaction.response.send_modal(modal)

    # ------------------------- Mode switching -------------------------

    async def to_container_button(self, interaction: discord.Interaction):
        items: list[dict] = []
        if self.content:
            items.append({"type": "text", "text": self.content})
        if self.embed:
            if self.embed.title:
                items.append({"type": "text", "text": f"## {self.embed.title}"})
            if self.embed.description:
                items.append({"type": "text", "text": self.embed.description})
            for field in self.embed.fields:
                items.append({"type": "text", "text": f"**{field.name}**\n{field.value}"})
            urls = [url for url in (self.embed.thumbnail.url, self.embed.image.url) if url]
            if urls:
                items.append({"type": "media", "urls": urls})
            if self.embed.colour:
                self.accent = self.embed.colour
        self.items = items or [{"type": "text", "text": "*empty*"}]
        self.mode = "container"
        await self.refresh(interaction)

    async def to_embed_button(self, interaction: discord.Interaction):
        texts = [item["text"] for item in self.items if item["type"] == "text"]
        description = "\n\n".join(texts)[:4000]
        embed = discord.Embed(description=description or None, colour=self.accent)
        media = next((item for item in self.items if item["type"] == "media"), None)
        if media:
            embed.set_image(url=media["urls"][0])
        self.embed = embed
        self.content = ""
        self.mode = "embed"
        await self.refresh(interaction)

    # ------------------------- Save / Cancel / Cleanup -------------------------

    async def apply_to_target(self) -> None:
        if self.mode == "embed":
            embeds = [self.embed] if self.embed else []
            await self.target.edit(content=self.content or None, embeds=embeds)
            return
        layout = SavedLayout(self.build_container())
        if self.locked_v2:
            await self.target.edit(view=layout)
        else:
            await self.target.edit(content=None, embeds=[], attachments=[], view=layout)

    async def save_button(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.apply_to_target()
        except discord.HTTPException as e:
            log.error(f"Failed to save edits to message {self.target.id}", exc_info=e)
            return await interaction.followup.send(f"Failed to save changes: {e}", ephemeral=True)
        await self.close()
        with suppress(discord.HTTPException):
            await interaction.followup.send("Message updated.", ephemeral=True)
        log.info(f"{self.user} full-edited message {self.target.id} in {self.target.guild}")

    async def cancel_button(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.close()
        with suppress(discord.HTTPException):
            await interaction.followup.send("Editor closed, no changes saved.", ephemeral=True)

    async def close(self) -> None:
        self.done = True
        if self.editor_msg:
            with suppress(discord.HTTPException):
                await self.editor_msg.delete()
            self.editor_msg = None

    async def expire(self) -> None:
        if not self.done:
            await self.close()
