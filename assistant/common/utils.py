import logging

import discord

log = logging.getLogger("red.vrt.assistant.utils")


def get_attachments(message: discord.Message) -> list[discord.Attachment]:
    """Get all attachments from context"""
    attachments = []
    if message.attachments:
        direct_attachments = [a for a in message.attachments]
        attachments.extend(direct_attachments)
    if hasattr(message, "reference"):
        try:
            referenced_attachments = [
                a for a in message.reference.resolved.attachments
            ]
            attachments.extend(referenced_attachments)
        except AttributeError:
            pass
    return attachments
