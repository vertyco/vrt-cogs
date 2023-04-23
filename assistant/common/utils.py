import logging

import discord
import tiktoken

log = logging.getLogger("red.vrt.assistant.utils")
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")


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


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(encoding.encode(string))
    return num_tokens
