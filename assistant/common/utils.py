import asyncio
import logging
import math
from typing import Dict, List, Union

import discord
import openai
import tiktoken
from aiocache import cached
from discord.app_commands import Choice
from retry import retry

log = logging.getLogger("red.vrt.assistant.utils")
encoding = tiktoken.get_encoding("cl100k_base")

@cached(ttl=120)
async def get_embedding_names(embeddings: List[str], current: str) -> List[Choice]:
    return [Choice(name=i, value=i) for i in embeddings if current.lower() in i.lower()]


def get_attachments(message: discord.Message) -> List[discord.Attachment]:
    """Get all attachments from context"""
    attachments = []
    if message.attachments:
        direct_attachments = [a for a in message.attachments]
        attachments.extend(direct_attachments)
    if hasattr(message, "reference"):
        try:
            referenced_attachments = [a for a in message.reference.resolved.attachments]
            attachments.extend(referenced_attachments)
        except AttributeError:
            pass
    return attachments


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    if not string:
        return 0
    num_tokens = len(encoding.encode(string))
    return num_tokens


async def fetch_channel_history(
    channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel],
    limit: int = 50,
    oldest: bool = True,
) -> List[discord.Message]:
    history = []
    async for msg in channel.history(oldest_first=oldest, limit=limit):
        history.append(msg)
    return history


def extract_message_content(message: discord.Message):
    content = ""
    if message.content:
        content += f"{content}\n"
    if message.embeds:
        content += f"{extract_embed_content(message.embeds)}\n"
    return content.strip()


def extract_embed_content(embeds: List[discord.Embed]) -> str:
    content = ""
    for embed in embeds:
        if title := embed.title:
            content += f"{title}\n"
        if desc := embed.description:
            content += f"{desc}\n"
        if fields := embed.fields:
            for field in fields:
                content += f"{field.name}\n{field.value}\n"
        if foot := embed.footer:
            content += f"{foot.text}\n"
    return content.strip()


def token_pagify(text: str, max_tokens: int = 2000):
    """Pagify a long string by tokens rather than characters"""
    token_chunks = []
    tokens = encoding.encode(text)
    current_chunk = []

    for token in tokens:
        current_chunk.append(token)
        if len(current_chunk) == max_tokens:
            token_chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        token_chunks.append(current_chunk)

    text_chunks = []
    for chunk in token_chunks:
        text_chunk = encoding.decode(chunk)
        text_chunks.append(text_chunk)

    return text_chunks


def embedding_embeds(embeddings: Dict[str, dict], place: int):
    embeddings = sorted(embeddings.items(), key=lambda x: x[0])
    embeds = []
    pages = math.ceil(len(embeddings) / 5)
    start = 0
    stop = 5
    for page in range(pages):
        stop = min(stop, len(embeddings))
        embed = discord.Embed(title="Embeddings", color=discord.Color.blue())
        embed.set_footer(text=f"Page {page + 1}/{pages}")
        num = 0
        for i in range(start, stop):
            em = embeddings[i]
            text = em[1]["text"]
            token_length = num_tokens_from_string(text)
            val = f"`Tokens: `{token_length}\n```\n{text[:30]}...\n```"
            embed.add_field(
                name=f"➣ {em[0]}" if place == num else em[0],
                value=val,
                inline=False,
            )
            num += 1
        embeds.append(embed)
        start += 5
        stop += 5
    if not embeds:
        embeds.append(
            discord.Embed(
                description="No embeddings have been added!", color=discord.Color.purple()
            )
        )
    return embeds


async def get_embedding_async(text: str, api_key: str) -> List[float]:
    return await asyncio.to_thread(get_embedding, text, api_key)


@retry(tries=3, delay=2)
def get_embedding(text: str, api_key: str) -> List[float]:
    response = openai.Embedding.create(input=text, model="text-embedding-ada-002", api_key=api_key)
    return response["data"][0]["embedding"]


async def get_chat_async(model: str, messages: list, api_key: str, temperature: float = 0) -> str:
    return await asyncio.to_thread(get_chat, model, messages, temperature, api_key)


@retry(tries=3, delay=3)
def get_chat(model: str, messages: list, api_key: str, temperature: float = 0) -> str:
    response = openai.ChatCompletion.create(
        model=model, messages=messages, temperature=temperature, api_key=api_key
    )
    return response["choices"][0]["message"]["content"]
