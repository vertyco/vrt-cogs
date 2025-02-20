import logging
import re
from typing import List, Optional

import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, text_to_file

from .models import GuildSettings

log = logging.getLogger("red.vrt.assistant.reply")
_ = Translator("Assistant", __file__)

CODE_BLOCK = re.compile(r"```(?P<lang>\w+)?\n?(?P<code>.*?)```", re.DOTALL)
THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL)


async def send_reply(
    message: discord.Message,
    content: str,
    conf: GuildSettings,
    files: Optional[List[discord.File]] = None,
    reply: bool = False,
):
    """Intelligently send a reply to a message

    Ensure the cleanest possible output is sent to the user
    Making sure not to break any markdown code blocks
    """
    # Handle thinking sections first
    if "<think>" in content:
        if files is None:
            files = []
        for idx, match in enumerate(THINK_BLOCK.finditer(content)):
            think_content = match.group(1).strip()
            if not think_content:
                think_content += "no thinkies 🤯"
            filename = "thinkies.txt" if idx == 0 else f"thinkies_part{idx + 1}.txt"
            files.append(text_to_file(think_content, filename=filename))
        content = THINK_BLOCK.sub("", content).strip()

    channel_perms = message.channel.permissions_for(message.guild.me)
    embed_perms = channel_perms.embed_links
    file_perms = channel_perms.attach_files
    if files and not file_perms:
        files = []
        content += _("\nMissing 'attach files' permissions!")

    async def send(
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        embeds: Optional[List[discord.Embed]] = None,
        files: Optional[List[discord.File]] = None,
        as_reply: bool = False,
        mention: bool = False,
    ):
        if files is None:
            files = []
        if as_reply:
            try:
                return await message.reply(
                    content=content,
                    embed=embed,
                    embeds=embeds,
                    files=files,
                    mention_author=mention,
                )
            except discord.HTTPException:
                pass
        try:
            await message.channel.send(content=content, embed=embed, embeds=embeds, files=files)
        except discord.HTTPException as e:
            log.error("Error sending message", exc_info=e)

    # Simple case: Content fits in a single message
    if len(content) <= 2000:
        return await send(content, files=files, as_reply=reply, mention=conf.mention)

    # Medium case: Content fits in a single embed and we have embed permissions
    elif len(content) <= 4000 and embed_perms and "```" not in content:
        return await send(embed=discord.Embed(description=content), files=files, as_reply=reply, mention=conf.mention)

    # Long content case without code blocks: Paginate into multiple messages
    elif "```" not in content:
        # Use longer pages if we can use embeds, otherwise stick to message length limit
        page_length = 4000 if embed_perms else 2000
        chunks = [p for p in pagify(content, page_length=page_length)]
        for idx, chunk in enumerate(chunks):
            kwargs = {}
            if embed_perms:
                kwargs["embed"] = discord.Embed(description=chunk)
            else:
                kwargs["content"] = chunk
            # Only include files and mention on first message
            if idx == 0:
                kwargs["mention"] = conf.mention
                kwargs["files"] = files
                kwargs["as_reply"] = reply
            await send(**kwargs)
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
    for idx, (type, text) in enumerate(segments):
        if type == "text":
            # Regular text can use embeds for larger chunks
            page_length = 4000 if embed_perms else 2000
            for chunk in pagify(text, page_length=page_length):
                kwargs = {}
                if len(chunk) >= 2000:
                    kwargs["embed"] = discord.Embed(description=chunk)
                else:
                    kwargs["content"] = chunk
                if idx == 0:
                    kwargs["mention"] = conf.mention
                    kwargs["files"] = files
                    kwargs["as_reply"] = reply
                await send(**kwargs)
        else:
            # For code blocks, pagify the inner content and wrap each chunk
            match = CODE_BLOCK.match(text)
            if match:
                lang = match.group("lang") or ""
                code = match.group("code")
                # Pagify just the code content
                lang_length = 6 + len(lang)
                for chunk in pagify(code, delims=("\n",), page_length=2000 - lang_length):
                    kwargs = {"content": f"```{lang}\n{chunk}```"}
                    if idx == 0:
                        kwargs["mention"] = conf.mention
                        kwargs["files"] = files
                        kwargs["as_reply"] = reply
                    await send(**kwargs)
