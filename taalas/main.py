import asyncio
import json
import logging

import aiohttp
import discord
import tiktoken
from redbot.core import Config, commands
from redbot.core.bot import Red

log = logging.getLogger("red.vrt.taalas")

API_BASE = "https://api.taalas.com"
MODEL = "llama3.1-8B"
TOKEN_LIMIT = 10000
# llama3.1 uses the same tokenizer base as GPT-4o
ENCODING = tiktoken.get_encoding("o200k_base")
# Per-message overhead: <|start|>role<|end|> framing
TOKENS_PER_MESSAGE = 4
# Every reply is primed with <|start|>assistant<|message|>
REPLY_PRIMER_TOKENS = 3


def count_message_tokens(messages: list[dict]) -> int:
    """Count tokens in a chat message list using tiktoken."""
    num_tokens = 0
    for message in messages:
        num_tokens += TOKENS_PER_MESSAGE
        for value in message.values():
            num_tokens += len(ENCODING.encode(str(value)))
    num_tokens += REPLY_PRIMER_TOKENS
    return num_tokens


def compact_messages(messages: list[dict]) -> list[dict]:
    """Drop oldest messages (in pairs when possible) until under TOKEN_LIMIT.

    Always preserves at least the most recent user message. Follows the
    openclaw pattern of removing from the front to keep recent context.
    """
    while count_message_tokens(messages) > TOKEN_LIMIT and len(messages) > 1:
        # Drop oldest message; prefer dropping user+assistant pairs together
        if len(messages) >= 2 and messages[0]["role"] == "user" and messages[1]["role"] == "assistant":
            messages.pop(0)
            messages.pop(0)
        else:
            messages.pop(0)
    return messages


class Taalas(commands.Cog):
    """Interact with the Taalas LLM API powered by custom silicon-embedded model weights."""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.3"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 4838572947, force_registration=True)
        self.config.register_user(scope="user")
        self.config.register_global(conversations={})
        self.session: aiohttp.ClientSession | None = None
        self.conversations: dict[str, list[dict[str, str]]] = {}

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        uid = str(user_id)
        keys_to_remove = [k for k in self.conversations if k == uid or k.endswith(f"-{uid}")]
        for key in keys_to_remove:
            del self.conversations[key]
        if keys_to_remove:
            await self.config.conversations.set(self.conversations)
        await self.config.user_from_id(user_id).clear()

    async def red_get_data_for_user(self, *, requester: str, user_id: int):
        return

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        self.session = aiohttp.ClientSession()
        self.conversations = await self.config.conversations()

    def convo_key(self, user_id: int, channel_id: int, scope: str) -> str:
        if scope == "channel":
            return f"{channel_id}-{user_id}"
        return str(user_id)

    async def get_api_key(self) -> str | None:
        tokens = await self.bot.get_shared_api_tokens("taalas")
        return tokens.get("api_key")

    def messages_to_prompt(self, messages: list[dict]) -> str:
        """Format a chat messages list into a single prompt string for non-chat endpoints."""
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    async def call_chat_completions(self, headers: dict, messages: list[dict]) -> str:
        """Try v1/chat/completions (messages array)."""
        payload = {"messages": messages, "model": MODEL, "stream": False}
        async with self.session.post(f"{API_BASE}/v1/chat/completions", headers=headers, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history, status=resp.status, message=body[:300]
                )
            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("API returned no choices.")
            return choices[0].get("message", {}).get("content", "")

    async def call_generate(self, headers: dict, prompt: str) -> str:
        """Try /generate (prompt string, SSE stream)."""
        payload = {"prompt": prompt, "model": MODEL, "stream": True}
        async with self.session.post(f"{API_BASE}/generate", headers=headers, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history, status=resp.status, message=body[:300]
                )
            response_text = ""
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if data.get("done"):
                    break
                response_text += data.get("response", "")
            return response_text

    async def call_completions(self, headers: dict, prompt: str) -> str:
        """Try v1/completions (prompt string, non-streaming)."""
        payload = {"prompt": prompt, "model": MODEL, "stream": False}
        async with self.session.post(f"{API_BASE}/v1/completions", headers=headers, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history, status=resp.status, message=body[:300]
                )
            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("API returned no choices.")
            return choices[0].get("text", "")

    async def chat(self, messages: list[dict]) -> str:
        """Call Taalas with fallback: chat/completions -> generate -> completions."""
        api_key = await self.get_api_key()
        if not api_key:
            raise ValueError(
                "No Taalas API key has been set.\nA bot owner needs to run: `[p]set api taalas api_key <key>`"
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        prompt = self.messages_to_prompt(messages)

        fallbacks = [
            ("v1/chat/completions", lambda: self.call_chat_completions(headers, messages)),
            ("generate", lambda: self.call_generate(headers, prompt)),
            ("v1/completions", lambda: self.call_completions(headers, prompt)),
        ]

        last_error: Exception | None = None
        for name, call in fallbacks:
            try:
                return await call()
            except (aiohttp.ClientResponseError, ValueError) as e:
                log.warning("Taalas %s failed: %s — trying next endpoint", name, e)
                last_error = e

        raise ValueError(f"All Taalas endpoints failed. Last error: {last_error}")

    def save(self) -> None:
        async def _save():
            try:
                await self.config.conversations.set(self.conversations)
            except Exception as e:
                log.exception("Failed to save conversations", exc_info=e)

        asyncio.create_task(_save())

    @commands.group(invoke_without_command=True)
    async def taalas(self, ctx: commands.Context, *, message: str):
        """Chat with the Taalas LLM.

        Conversation history is preserved between messages.
        Use `[p]taalas clearconvo` to start fresh.
        Use `[p]taalas scope` to toggle per-user vs per-channel conversations.
        """
        if not self.session:
            await ctx.send("Taalas is still initializing, please try again in a moment.")
            return

        scope = await self.config.user(ctx.author).scope()
        key = self.convo_key(ctx.author.id, ctx.channel.id, scope)

        messages = list(self.conversations.get(key, []))
        messages.append({"role": "user", "content": message})
        messages = compact_messages(messages)

        async with ctx.typing():
            try:
                response = await self.chat(messages)
            except ValueError as e:
                await ctx.send(str(e))
                return

        if not response:
            await ctx.send("Received an empty response from the API.")
            return

        messages.append({"role": "assistant", "content": response})
        messages = compact_messages(messages)
        self.conversations[key] = messages
        self.save()

        # Send response, respecting Discord's 2000-char limit
        no_mentions = discord.AllowedMentions.none()
        for i in range(0, len(response), 2000):
            await ctx.send(response[i : i + 2000], allowed_mentions=no_mentions)

    @taalas.command(name="health")
    async def taalas_health(self, ctx: commands.Context):
        """Check the Taalas API health status."""
        if not self.session:
            await ctx.send("Taalas is still initializing, please try again in a moment.")
            return

        try:
            async with self.session.get(f"{API_BASE}/health") as resp:
                if resp.status != 200:
                    await ctx.send(f"Health check failed with status {resp.status}.")
                    return
                data = await resp.json()
        except aiohttp.ClientError as e:
            await ctx.send(f"Failed to reach the Taalas API: {e}")
            return

        status = data.get("status", "unknown")
        queue_size = data.get("queue_size", "?")
        adapter = data.get("current_adapter", "unknown")
        await ctx.send(f"**Taalas API**\nStatus: `{status}`\nQueue size: `{queue_size}`\nAdapter: `{adapter}`")

    @taalas.command(name="clearconvo")
    async def taalas_clearconvo(self, ctx: commands.Context):
        """Clear your conversation history."""
        scope = await self.config.user(ctx.author).scope()
        key = self.convo_key(ctx.author.id, ctx.channel.id, scope)

        if key in self.conversations:
            del self.conversations[key]
            self.save()

        await ctx.send("Your conversation has been cleared.")

    @taalas.command(name="scope")
    async def taalas_scope(self, ctx: commands.Context):
        """Toggle conversation scope between per-user and per-channel.

        **Per-user**: Same conversation history everywhere.
        **Per-channel**: Separate conversation in each channel.
        """
        current = await self.config.user(ctx.author).scope()
        new_scope = "channel" if current == "user" else "user"
        await self.config.user(ctx.author).scope.set(new_scope)
        label = "per-channel" if new_scope == "channel" else "per-user"
        await ctx.send(f"Conversation scope set to **{label}**.")
