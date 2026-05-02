import logging
import re
from pathlib import Path
from typing import List, Optional

import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, text_to_file

from .models import GuildSettings

log = logging.getLogger("red.vrt.assistant.reply")
_ = Translator("Assistant", __file__)

CODE_BLOCK = re.compile(r"```(?P<lang>\w+)?\n?(?P<code>.*?)```", re.DOTALL)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}


def get_think_block_pattern(conf: GuildSettings) -> Optional[re.Pattern[str]]:
    if not conf.think_tag_prefix or not conf.think_tag_suffix:
        return None
    return re.compile(
        f"{re.escape(conf.think_tag_prefix)}(.*?){re.escape(conf.think_tag_suffix)}",
        re.DOTALL,
    )


def extract_think_blocks(content: str, conf: GuildSettings) -> tuple[str, List[discord.File]]:
    pattern = get_think_block_pattern(conf)
    if pattern is None:
        return content, []

    if conf.think_tag_prefix not in content or conf.think_tag_suffix not in content:
        return content, []

    files: List[discord.File] = []
    for idx, match in enumerate(pattern.finditer(content)):
        think_content = match.group(1).strip() or "no thinkies 🤯"
        filename = "thinkies.txt" if idx == 0 else f"thinkies_part{idx + 1}.txt"
        files.append(text_to_file(think_content, filename=filename))

    if not files:
        return content, []

    return pattern.sub("", content).strip(), files


def split_attachment_files(files: Optional[List[discord.File]]) -> tuple[List[discord.File], List[discord.File]]:
    if not files:
        return [], []

    image_files: List[discord.File] = []
    other_files: List[discord.File] = []
    for file in files:
        filename = getattr(file, "filename", None)
        if filename and Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
            image_files.append(file)
        else:
            other_files.append(file)
    return image_files, other_files


def make_text_view(content: str, files: Optional[List[discord.File]] = None) -> Optional[discord.ui.LayoutView]:
    view = discord.ui.LayoutView(timeout=None)
    if content:
        view.add_item(discord.ui.TextDisplay(content))

    if files:
        image_items: list[discord.MediaGalleryItem] = []
        for file in files:
            filename = getattr(file, "filename", None)
            if not filename:
                continue
            if Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
                image_items.append(discord.MediaGalleryItem(f"attachment://{filename}"))

        if image_items:
            view.add_item(discord.ui.MediaGallery(*image_items))

    return view if view.children else None


async def send_reply(
    message: discord.Message,
    content: str,
    conf: GuildSettings,
    files: Optional[List[discord.File]] = None,
    reply: bool = False,
    allowed_mentions: Optional[discord.AllowedMentions] = None,
):
    """Intelligently send a reply to a message

    Ensure the cleanest possible output is sent to the user
    Making sure not to break any markdown code blocks
    """
    # Handle thinking sections first
    content, think_files = extract_think_blocks(content, conf)
    if think_files:
        if files is None:
            files = []
        files.extend(think_files)

    channel_perms = message.channel.permissions_for(message.guild.me)
    file_perms = channel_perms.attach_files
    if files and not file_perms:
        files = []
        content += _("\nMissing 'attach files' permissions!")

    async def send(
        content: Optional[str] = None,
        view: Optional[discord.ui.LayoutView] = None,
        files: Optional[List[discord.File]] = None,
        as_reply: bool = False,
        mention: bool = False,
    ):
        if files is None:
            files = []
        kwargs = {"allowed_mentions": allowed_mentions}
        if content:
            kwargs["content"] = content
        if view is not None:
            kwargs["view"] = view
        if files:
            kwargs["files"] = files
        if as_reply:
            try:
                return await message.reply(
                    mention_author=mention,
                    **kwargs,
                )
            except discord.HTTPException:
                pass
        try:
            await message.channel.send(**kwargs)
        except discord.HTTPException as e:
            log.error("Error sending message", exc_info=e)

    image_files, attachment_files = split_attachment_files(files)

    if not content:
        if image_files:
            await send(view=make_text_view("", image_files), files=image_files, as_reply=reply, mention=conf.mention)
            if attachment_files:
                await send(files=attachment_files)
            return
        if attachment_files:
            return await send(files=attachment_files, as_reply=reply, mention=conf.mention)
        return

    if attachment_files and not image_files and len(content) <= 2000:
        return await send(content=content, files=attachment_files, as_reply=reply, mention=conf.mention)

    # Simple case: Content fits in a single text display
    if len(content) <= 4000 and "```" not in content:
        await send(view=make_text_view(content, image_files), files=image_files, as_reply=reply, mention=conf.mention)
        if attachment_files:
            await send(files=attachment_files)
        return

    # Long content case without code blocks: Paginate into multiple messages
    elif "```" not in content:
        chunks = [p for p in pagify(content, page_length=4000)]
        for idx, chunk in enumerate(chunks):
            first_files = image_files if idx == 0 else None
            kwargs = {"view": make_text_view(chunk, first_files)}
            # Only include files and mention on first message
            if idx == 0:
                kwargs["mention"] = conf.mention
                kwargs["files"] = image_files
                kwargs["as_reply"] = reply
            await send(**kwargs)
        if attachment_files:
            await send(files=attachment_files)
        return

    # Complex case: Content contains code blocks that need special handling
    # Split content into segments of regular text and code blocks while preserving formatting
    segments = []
    last_end = 0

    # Find and separate code blocks from regular text
    for match in CODE_BLOCK.finditer(content):
        # Capture any text that appears before this code block
        if match.start() > last_end:
            segments.append(("text", content[last_end : match.start()]))

        # Preserve the code block with its language and formatting
        lang = match.group("lang") or ""
        code = match.group("code")
        segments.append(("code", f"```{lang}\n{code}```"))
        last_end = match.end()

    # Add any remaining text after the last code block
    if last_end < len(content):
        segments.append(("text", content[last_end:]))

    # Process and send each segment appropriately
    first_message_sent = False
    for segment_type, text in segments:
        if segment_type == "text":
            for chunk in pagify(text, page_length=4000):
                first_files = image_files if not first_message_sent else None
                kwargs = {"view": make_text_view(chunk, first_files)}
                if not first_message_sent:
                    kwargs["mention"] = conf.mention
                    kwargs["files"] = image_files
                    kwargs["as_reply"] = reply
                    first_message_sent = True
                await send(**kwargs)
        else:
            # For code blocks, pagify the inner content and wrap each chunk
            match = CODE_BLOCK.match(text)
            if match:
                lang = match.group("lang") or ""
                code = match.group("code")
                # Pagify just the code content
                wrapper_length = 7 + len(lang)
                for chunk in pagify(code, delims=("\n",), page_length=4000 - wrapper_length):
                    formatted = f"```{lang}\n{chunk}```"
                    first_files = image_files if not first_message_sent else None
                    kwargs = {"view": make_text_view(formatted, first_files)}
                    if not first_message_sent:
                        kwargs["mention"] = conf.mention
                        kwargs["files"] = image_files
                        kwargs["as_reply"] = reply
                        first_message_sent = True
                    await send(**kwargs)
    if attachment_files:
        await send(files=attachment_files)
