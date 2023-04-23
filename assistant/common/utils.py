import logging

import discord

log = logging.getLogger("red.vrt.assistant.utils")


def get_attachments(message: discord.Message) -> list[discord.Attachment]:
    """Get all attachments from context"""
    content = []
    if message.attachments:
        atchmts = [a for a in message.attachments]
        content.extend(atchmts)
    if hasattr(message, "reference"):
        try:
            atchmts = [a for a in message.reference.resolved.attachments]
            content.extend(atchmts)
        except AttributeError:
            pass
    return content
