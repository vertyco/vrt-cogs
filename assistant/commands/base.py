import asyncio
import json
import logging
import traceback
import typing as t
from base64 import b64decode
from contextlib import suppress
from datetime import datetime, timedelta
from io import BytesIO, StringIO

import discord
import httpx
import openai
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from redbot.core import app_commands, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    box,
    escape,
    humanize_list,
    humanize_timedelta,
    pagify,
    text_to_file,
)

from ..abc import MixinMeta
from ..common.calls import request_image_raw
from ..common.constants import IMAGE_COSTS, LOADING, READ_EXTENSIONS, TLDR_PROMPT
from ..common.models import Conversation
from ..common.utils import can_use, get_attachments

log = logging.getLogger("red.vrt.assistant.base")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class Base(MixinMeta):
    @commands.command(name="chathelp")
    async def chat_help(self, ctx: commands.Context):
        """Get help using assistant"""
        txt = (
            _(
                """
# How to Use

### Commands
`[p]convostats` - view your conversation message count/token usage for that convo.
`[p]clearconvo` - reset your conversation for the current channel/thread/forum.
`[p]showconvo` - get a json dump of your current conversation (this is mostly for debugging)
`[p]chat` or `[p]ask` - command prefix for chatting with the bot outside of the live chat, or just @ it.

### Chat Arguments
`[p]chat --last` - resend the last message of the conversation.
`[p]chat --extract` - extract all markdown text to be sent as a separate message.
`[p]chat --outputfile <filename>` - sends the reply as a file instead.

### Argument Use-Cases
`[p]chat --last --outpufile test.py` - output the last message the bot sent as a file.
`[p]chat write a python script to do X... --extract --outputfile test.py` - all code blocks from the output will be sent as a file in addition to the reply.
`[p]chat --last --extract --outputfile test.py` - extract code blocks from the last message to send as a file.

### File Comprehension
Files may be uploaded with the chat command to be included with the question or query, so rather than pasting snippets, the entire file can be uploaded so that you can ask a question about it.
At the moment the bot is capable of reading the following file extensions.
```json
{}
```
If a file has no extension it will still try to read it only if it can be decoded to utf-8.
### Tips
- Replying to someone else's message while using the `[p]chat` command will include their message in *your* conversation, useful if someone says something helpful and you want to include it in your current convo with GPT.
- Replying to a message with a file attachment will have that file be read and included in your conversation. Useful if you upload a file and forget to use the chat command with it, or if someone else uploads a file you want to query the bot with.
- Conversations are *Per* user *Per* channel, so each channel you interact with GPT in is a different convo.
- Talking to the bot like a person rather than a search engine generally yields better results. The more verbose you can be, the better.
- Conversations are persistent, if you want the bot to forget the convo so far, use the `[p]clearconvo` command
        """
            )
            .replace("[p]", ctx.clean_prefix)
            .format(humanize_list(READ_EXTENSIONS))
        )
        embed = discord.Embed(description=txt.strip(), color=ctx.me.color)
        await ctx.send(embed=embed)

    @app_commands.command(name="draw", description=_("Generate an image with AI"))
    @app_commands.describe(prompt=_("What would you like to draw?"))
    @app_commands.describe(size=_("The size of the image to generate"))
    @app_commands.describe(quality=_("The quality of the image to generate"))
    @app_commands.describe(style=_("The style of the image to generate"))
    @app_commands.describe(model=_("The model to use for image generation"))
    @commands.guild_only()
    async def draw(
        self,
        interaction: discord.Interaction,
        prompt: str,
        size: t.Literal["1024x1024", "1792x1024", "1024x1792", "1024x1536", "1536x1024"] = "1024x1024",
        quality: t.Literal["low", "medium", "high", "standard", "hd"] = "medium",
        style: t.Literal["natural", "vivid"] = "vivid",
        model: t.Literal["dall-e-3", "gpt-image-1"] = "dall-e-3",
    ):
        conf = self.db.get_conf(interaction.guild)
        if self.db.endpoint_override:
            return await interaction.response.send_message(
                _("Image generation is not available when using custom endpoints"), ephemeral=True
            )
        if not conf.api_key and not self.db.endpoint_override:
            return await interaction.response.send_message(_("The API key is not set up!"), ephemeral=True)
        if not conf.image_command:
            return await interaction.response.send_message(_("Image generation is disabled!"), ephemeral=True)

        # Model-specific parameter validation
        if model == "gpt-image-1" and quality in ["standard", "hd"]:
            quality = "medium"  # Default for gpt-image-1 if dall-e-3 quality is provided
        if model == "dall-e-3" and quality in ["low", "medium", "high"]:
            quality = "standard"  # Default for dall-e-3 if gpt-image-1 quality is provided

        color = await self.bot.get_embed_color(interaction.channel)
        embed = discord.Embed(description=_("Generating image..."), color=color)
        embed.set_thumbnail(url=LOADING)
        await interaction.response.send_message(embed=embed)

        desc = _("-# Size: {}\n-# Quality: {}\n-# Model: {}").format(size, quality, model)
        if model == "dall-e-3":
            desc += _("\n-# Style: {}").format(style)

        cost_key = f"{quality}{size}"
        cost = IMAGE_COSTS.get(cost_key, 0)

        image = await request_image_raw(
            prompt, conf.api_key, size, quality, style, model, base_url=self.db.endpoint_override
        )

        image_bytes = b64decode(image.b64_json)
        file = discord.File(BytesIO(image_bytes), filename="image.png")
        embed = discord.Embed(description=desc, color=color)
        embed.set_image(url="attachment://image.png")
        embed.set_footer(text=_("Cost: ${}").format(f"{cost:.2f}"))

        if hasattr(image, "revised_prompt") and image.revised_prompt:
            chunks = [p for p in pagify(image.revised_prompt, page_length=1000)]
            for idx, chunk in enumerate(chunks):
                embed.add_field(name=_("Revised Prompt") if idx == 0 else _("Continued"), value=chunk, inline=False)

        await interaction.edit_original_response(embed=embed, attachments=[file])

    @commands.command(
        name="chat",
        aliases=[
            "ask",
            "escribir",
            "razgovor",
            "discuter",
            "plaudern",
            "채팅",
            "charlar",
            "baterpapo",
            "sohbet",
        ],
    )
    @commands.guild_only()
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def ask_question(self, ctx: commands.Context, *, question: str):
        """
        Chat with [botname]!

        Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel

        **Optional Arguments**
        `--outputfile <filename>` - uploads a file with the reply instead (no spaces)
        `--extract` - extracts code blocks from the reply
        `--last` - resends the last message of the conversation

        **Example**
        `[p]chat write a python script that prints "Hello World!"`
        - Including `--outputfile hello.py` will output a file containing the whole response.
        - Including `--outputfile hello.py --extract` will output a file containing just the code blocks and send the rest as text.
        - Including `--extract` will send the code separately from the reply
        """
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return
        if not await can_use(ctx.message, conf.blacklist):
            return
        async with ctx.typing():
            await self.handle_message(ctx.message, question, conf)

    @commands.command(name="convostats")
    @commands.guild_only()
    async def show_convo_stats(self, ctx: commands.Context, *, user: discord.Member = None):
        """
        Check the token and message count of yourself or another user's conversation for this channel

        Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel

        Conversations are only stored in memory until the bot restarts or the cog reloads
        """
        if not user:
            user = ctx.author
        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else user.id
        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        messages = len(conversation.messages)

        max_tokens = self.get_max_tokens(conf, ctx.author)

        def generate_color(index: int, limit: int):
            if not limit:
                return (0, 0)
            if index > limit:
                return (0, 0)

            # RGB for white is (255, 255, 255) and for red is (255, 0, 0)
            # As we progress from white to red, we need to decrease the values of green and blue from 255 to 0

            # Calculate the decrement in green and blue values
            decrement = int((255 / limit) * index)

            # Calculate the new green and blue values
            green = blue = 255 - decrement

            # Return the new RGB color
            return (green, blue)

        convo_tokens = await self.count_payload_tokens(
            conversation.messages,
            conf.get_chat_model(
                self.db.endpoint_override, user, self.db.ollama_models or None, self.db.endpoint_is_ollama
            ),
        )
        g, b = generate_color(messages, conf.get_user_max_retention(ctx.author))
        gg, bb = generate_color(convo_tokens, max_tokens)
        # Whatever limit is more severe get that color
        color = discord.Color.from_rgb(255, min(g, gg), min(b, bb))
        model = conf.get_chat_model(
            self.db.endpoint_override, ctx.author, self.db.ollama_models or None, self.db.endpoint_is_ollama
        )

        desc = (
            ctx.channel.mention
            + "\n"
            + _("`Messages:   `{}/{}\n`Tokens:     `{}/{}\n`Expired:    `{}\n`Model:      `{}").format(
                messages,
                conf.get_user_max_retention(ctx.author),
                convo_tokens,
                max_tokens,
                conversation.is_expired(conf, ctx.author),
                model,
            )
        )
        desc += _("\n`Tool Calls: `{}").format(conversation.function_count())
        if conf.collab_convos:
            desc += "\n" + _("*Collabroative conversations are enabled*")
        embed = discord.Embed(
            description=desc,
            color=color,
        )
        embed.set_author(
            name=_("Conversation stats for {}").format(ctx.channel.name if conf.collab_convos else user.display_name),
            icon_url=ctx.guild.icon if conf.collab_convos else user.display_avatar,
        )
        embed.set_footer(text=_("Token limit is a soft cap and excess is trimmed before sending to the api"))
        await ctx.send(embed=embed)
        if await self.bot.is_mod(ctx.author) or ctx.author.id in self.bot.owner_ids or not conf.collab_convos:
            if conversation.system_prompt_override:
                file = text_to_file(conversation.system_prompt_override)
                await ctx.send(_("System prompt override for this conversation"), file=file)
            elif ctx.channel.id in conf.channel_prompts:
                file = text_to_file(conf.channel_prompts[ctx.channel.id])
                await ctx.send(_("System prompt override for this channel"), file=file)

    @commands.command(name="convoclear", aliases=["clearconvo"])
    @commands.guild_only()
    async def clear_convo(self, ctx: commands.Context):
        """
        Reset your conversation with the bot

        This will clear all message history between you and the bot for this channel
        """
        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else ctx.author.id
        perms = [
            await self.bot.is_mod(ctx.author),
            ctx.channel.permissions_for(ctx.author).manage_messages,
            ctx.author.id in self.bot.owner_ids,
        ]
        if conf.collab_convos and not any(perms):
            txt = _("Only moderators can clear channel conversations when collaborative conversations are enabled!")
            return await ctx.send(txt)
        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        conversation.reset()
        await ctx.send(_("Your conversation in this channel has been reset!"))

    @commands.command(name="convopop")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(attach_files=True)
    async def pop_last_message(self, ctx: commands.Context):
        """
        Pop the last message from your conversation
        """
        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else ctx.author.id
        perms = [
            await self.bot.is_mod(ctx.author),
            ctx.channel.permissions_for(ctx.author).manage_messages,
            ctx.author.id in self.bot.owner_ids,
        ]
        if conf.collab_convos and not any(perms):
            txt = _("Only moderators can pop messages from conversations when collaborative conversations are enabled!")
            return await ctx.send(txt)
        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        if not conversation.messages:
            txt = _("There are no messages in this conversation yet!")
            return await ctx.send(txt)
        last = conversation.messages.pop()
        dump = json.dumps(last, indent=2)
        file = text_to_file(dump, "popped.json")
        await ctx.send(_("Removed the last message from this conversation"), file=file)

    @app_commands.command(name="tldr", description=_("Summarize whats been happening in a channel"))
    @app_commands.guild_only()
    @app_commands.describe(
        timeframe=_("The number of messages to scan"),
        question=_("Ask for specific info about the conversation"),
        channel=_("The channel to summarize messages from"),
        member=_("Target a specific member"),
        private=_("Only you can see the response"),
    )
    async def summarize_convo(
        self,
        interaction: discord.Interaction,
        timeframe: t.Optional[str] = "1h",
        question: t.Optional[str] = None,
        channel: t.Optional[discord.TextChannel] = None,
        member: t.Optional[discord.Member] = None,
        private: t.Optional[bool] = True,
    ):
        """
        Get a summary of whats going on in a channel
        """
        delta = commands.parse_timedelta(timeframe)
        channel = channel or interaction.channel
        if not delta:
            txt = _("Invalid timeframe! Please use a valid time format like `1h` for an hour")
            return await interaction.response.send_message(txt, ephemeral=True)
        if delta > timedelta(hours=48):
            txt = _("The maximum timeframe is 48 hours!")
            return await interaction.response.send_message(txt, ephemeral=True)
        perms = [
            await self.bot.is_mod(interaction.user),
            interaction.channel.permissions_for(interaction.user).manage_messages,
            interaction.user.id in self.bot.owner_ids,
        ]
        if not any(perms):
            txt = _("Only moderators can summarize conversations!")
            return await interaction.response.send_message(txt, ephemeral=True)
        user_allowed = [
            channel.permissions_for(interaction.user).view_channel,
            channel.permissions_for(interaction.user).read_message_history,
        ]
        if not all(user_allowed):
            txt = _("You don't have permission to view the channel!")
            return await interaction.response.send_message(txt, ephemeral=True)
        bot_allowed = [
            channel.permissions_for(interaction.guild.me).view_channel,
            channel.permissions_for(interaction.guild.me).read_message_history,
        ]
        if not all(bot_allowed):
            txt = _("I don't have permission to view the channel!")
            return await interaction.response.send_message(txt, ephemeral=True)

        with suppress(discord.NotFound):
            if private:
                await interaction.response.defer(ephemeral=True, thinking=True)
            else:
                await interaction.response.defer(ephemeral=False, thinking=True)

        messages: t.List[discord.Message] = []
        async for message in channel.history(oldest_first=False):
            if member and message.author.id != member.id:
                continue
            if not message.content and not message.attachments:
                continue
            if not message.content and not any(a.content_type.startswith("image") for a in message.attachments):
                continue
            messages.append(message)
            now = datetime.now().astimezone()
            if now - message.created_at > delta:
                break

        if not messages:
            return await interaction.followup.send(_("No messages found to summarize within that timeframe!"))
        if len(messages) < 5:
            return await interaction.followup.send(_("Not enough messages found to summarize within that timeframe!"))

        conf = self.db.get_conf(interaction.guild)

        humanized_delta = humanize_timedelta(timedelta=delta)

        primer = (
            f"Your name is '{self.bot.user.name}' and you are a discord bot. Refer to yourself as 'I' or 'me' in your responses.\n"
            f"{TLDR_PROMPT}"
            f"Dont include the following info in the summary:\n"
            f"- guild_id: {interaction.guild.id}\n"
            f"- channel_id: {channel.id}\n"
            f"- Channel Name: {channel.name}\n"
            f"- Timeframe: {humanized_delta}\n"
        )
        if question:
            primer += f"- User prompt: {question}\n"

        payload = [{"role": "developer", "content": primer}]

        for message in reversed(messages):
            # Cleanup the message content
            for mention in message.mentions:
                message.content = message.content.replace(f"<@{mention.id}>", f"{mention.name} (<@{mention.id}>)")
            for mention in message.channel_mentions:
                message.content = message.content.replace(f"<#{mention.id}>", f"{mention.name} (<@{mention.id}>)")
            for mention in message.role_mentions:
                message.content = message.content.replace(f"<@&{mention.id}>", f"{mention.name} (<@{mention.id}>)")

            # created = message.created_at.strftime("%m-%d-%Y %I:%M %p")
            created_ts = f"<t:{int(message.created_at.timestamp())}:t>"

            detail = f"[{created_ts}]({message.id}) {message.author.name}"

            ref: t.Optional[discord.Message] = None
            if hasattr(message, "reference") and message.reference:
                ref = message.reference.resolved

            if ref:
                detail += f" (replying to {ref.author.name} at {ref.id})"

            if message.content:
                detail += f": {message.content}"
            elif message.embeds:
                detail += "\n# EMBED\n"
                embed = message.embeds[0]
                if embed.title:
                    detail += f"Title: {embed.title}\n"
                if embed.description:
                    detail += f"Description: {embed.description}\n"
                for field in embed.fields:
                    detail += f"{field.name}: {field.value}\n"
                if embed.footer:
                    detail += f"Footer: {embed.footer.text}\n"

            if not message.attachments:
                payload.append({"role": "user", "content": detail, "name": str(message.author.id)})
            else:
                message_obj = {
                    "role": "user",
                    "name": str(message.author.id),
                    "content": [{"type": "text", "text": detail}],
                }
                for attachment in message.attachments:
                    # Make sure the attachment is an image
                    if attachment.content_type.startswith("image"):
                        message_obj["content"].append(
                            {
                                "type": "image_url",
                                "image_url": {"url": attachment.url, "detail": conf.vision_detail},
                            }
                        )
                    elif attachment.content_type.startswith("text") and attachment.filename.endswith(
                        tuple(READ_EXTENSIONS)
                    ):
                        try:
                            content = await attachment.read()
                            content = content.decode()
                            message_obj["content"].append(
                                {
                                    "type": "text",
                                    "text": f"```{attachment.filename.split('.')[-1]}\n{content}```",
                                }
                            )
                        except UnicodeDecodeError:
                            pass
                        except Exception as e:
                            log.error("Failed to read attachment for TLDR", exc_info=e)

                if message_obj["content"]:
                    payload.append(message_obj)

        try:
            response: ChatCompletionMessage = await self.request_response(
                messages=payload,
                conf=conf,
                model_override="gpt-5.1",
                temperature_override=0.0,
            )
        except httpx.ReadTimeout:
            return await interaction.followup.send(_("The request timed out!"))
        except openai.BadRequestError as e:
            error = e.body.get("message", "Unknown Error")
            kwargs = {}
            if interaction.user.id in self.bot.owner_ids:
                dump = json.dumps(payload, indent=2)
                file = text_to_file(dump, "payload.json")
                kwargs["file"] = file
            return await interaction.followup.send(f"BadRequest({e.status_code}): {error}", **kwargs)
        except Exception as e:
            log.error("Failed to get TLDR response", exc_info=e)
            return await interaction.followup.send(_("Failed to get response"))

        if not response.content:
            return await interaction.followup.send(_("No response was generated!"))

        split = [i.strip() for i in response.content.split("\n") if i.strip()]
        # We want to compress the spaced out bullet points while keeping the tldr header with two new lines
        description = split[0] + "\n\n" + "\n".join(split[1:])

        embed = discord.Embed(
            color=await self.bot.get_embed_color(interaction.channel),
            description=description,
        )
        embed.set_footer(text=_("Timeframe: {}").format(humanized_delta))
        if channel.id != interaction.channel.id:
            embed.add_field(name=_("Channel"), value=channel.mention)
        await interaction.followup.send(embed=embed)

        # if private:
        #     try:
        #         channel = await modlog.get_modlog_channel(interaction.guild)
        #         embed.title = _("TLDR Summary")
        #         embed.add_field(name=_("Channel"), value=interaction.channel.mention)
        #         embed.add_field(name=_("Messages"), value=len(messages))
        #         embed.add_field(name=_("Timeframe"), value=humanized_delta)
        #         embed.add_field(name=_("Moderator"), value=interaction.user.mention)
        #         await channel.send(embed=embed)
        #     except RuntimeError:
        #         pass

    @commands.command(name="convocopy")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(attach_files=True)
    async def copy_conversation(
        self, ctx: commands.Context, *, channel: discord.TextChannel | discord.Thread | discord.ForumChannel
    ):
        """
        Copy the conversation to another channel, thread, or forum
        """
        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else ctx.author.id
        perms = [
            await self.bot.is_mod(ctx.author),
            ctx.channel.permissions_for(ctx.author).manage_messages,
            ctx.author.id in self.bot.owner_ids,
        ]
        if conf.collab_convos and not any(perms):
            txt = _("Only moderators can copy conversations when collaborative conversations are enabled!")
            return await ctx.send(txt)

        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        conversation.cleanup(conf, ctx.author)
        conversation.refresh()

        if not conversation.messages:
            txt = _("There are no messages in this conversation yet!")
            return await ctx.send(txt)
        if not channel.permissions_for(ctx.author).view_channel:
            txt = _("You cannot copy a conversation to a channel you can't see!")
            return await ctx.send(txt)

        new_mem_id = channel.id if conf.collab_convos else ctx.author.id
        key = f"{new_mem_id}-{channel.id}-{ctx.guild.id}"
        if key in self.db.conversations:
            txt = _("This conversation has been overwritten in {}").format(channel.mention)
        else:
            txt = _("This conversation has been copied over to {}").format(channel.mention)
        await ctx.send(txt)

        self.db.conversations[key] = Conversation.model_validate(conversation.model_dump())

        await self.save_conf()

    @commands.command(name="convoprompt")
    @commands.guild_only()
    async def conversation_prompt(self, ctx: commands.Context, *, prompt: str = None):
        """
        Set a system prompt for this conversation!

        This allows customization of assistant behavior on a per channel basis!

        Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.allow_sys_prompt_override:
            txt = _("Conversation system prompt overriding is **Disabled**.")
            return await ctx.send(txt)

        mem_id = ctx.channel.id if conf.collab_convos else ctx.author.id
        perms = [
            await self.bot.is_mod(ctx.author),
            ctx.channel.permissions_for(ctx.author).manage_messages,
            ctx.author.id in self.bot.owner_ids,
        ]
        if conf.collab_convos and not any(perms):
            txt = _("Only moderators can set conversation prompts when collaborative conversations are enabled!")
            return await ctx.send(txt)

        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                prompt = (await attachments[0].read()).decode()
            except Exception as e:
                txt = _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                    attachments[0].filename, f"{ctx.clean_prefix}traceback"
                )
                await ctx.send(txt)
                log.error("Failed to parse conversation prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()
                return

        model = conf.get_chat_model(
            self.db.endpoint_override, ctx.author, self.db.ollama_models or None, self.db.endpoint_is_ollama
        )
        ptokens = await self.count_tokens(conf.prompt, model) if conf.prompt else 0
        max_tokens = conf.get_user_max_tokens(ctx.author)
        if ptokens > (max_tokens * 0.9):
            txt = _(
                "This prompt is uses {} tokens which is more than 90% of the maximum tokens allowed per conversation!\n"
                "Write a prompt using {} tokens or less to leave 10% of your token limit for responses"
            ).format(ptokens, round(max_tokens * 0.9))
            return await ctx.send(txt)

        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        conversation.system_prompt_override = prompt
        if prompt:
            txt = _("System prompt has been set for this conversation!")
        else:
            txt = _("System prompt has been **Removed** for this conversation!")
        await ctx.send(txt)

    @commands.command(name="convoshow", aliases=["showconvo"])
    @commands.guild_only()
    @commands.guildowner()
    async def show_convo(
        self,
        ctx: commands.Context,
        user: t.Optional[discord.Member] = None,
        channel: discord.TextChannel = commands.CurrentChannel,
    ):
        """
        View the current transcript of a conversation

        This is mainly here for moderation purposes
        """
        if not user:
            user = ctx.author

        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else user.id
        conversation = self.db.get_conversation(mem_id, channel.id, ctx.guild.id)
        if not conversation.messages:
            return await ctx.send(_("You have no conversation in this channel!"))

        if await self.bot.is_mod(user) or ctx.author.id in self.bot.owner_ids:
            dump = json.dumps(conversation.messages, indent=2)
            file = text_to_file(dump, "conversation.json")
        else:
            buffer = StringIO()
            for message in conversation.messages:
                name = message.get("name", message["role"])
                content = message["content"]
                buffer.write(f"{name}: {content}\n")
            file = text_to_file(buffer.getvalue(), "conversation.txt")

        await ctx.send(_("Here is your conversation transcript!"), file=file)

    @commands.command(name="importconvo")
    @commands.guild_only()
    @commands.guildowner()
    async def import_conversation(self, ctx: commands.Context):
        """
        Import a conversation from a file
        """
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(_("Please attach a file to import the conversation from!"))
        if len(attachments) > 1:
            return await ctx.send(_("Please only attach one file to import the conversation from!"))
        attachment = attachments[0]
        if not attachment.filename.endswith(".json"):
            return await ctx.send(_("Please upload a valid JSON file."))
        try:
            data = await attachment.read()
            messages = json.loads(data)
        except Exception as e:
            await ctx.send(_("Failed to parse conversation file."))
            log.error("Failed to parse conversation file", exc_info=e)
            return
        # Verify that it is a list of messages (dicts)
        if not isinstance(messages, list) or not all(isinstance(msg, dict) for msg in messages):
            return await ctx.send(
                _("The conversation file is not in the correct format. It should be a list of messages.")
            )
        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else ctx.author.id
        perms = [
            await self.bot.is_mod(ctx.author),
            ctx.channel.permissions_for(ctx.author).manage_messages,
            ctx.author.id in self.bot.owner_ids,
        ]
        if not any(perms) and conf.collab_convos:
            return await ctx.send(_("You do not have permission to import conversations."))

        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        conversation.messages = messages

        await ctx.send(_("Conversation has been imported successfully!"))
        await self.save_conf()

    @commands.command(name="query")
    @commands.bot_has_permissions(embed_links=True)
    async def test_embedding_response(self, ctx: commands.Context, *, query: str):
        """
        Fetch related embeddings according to the current topn setting along with their scores

        You can use this to fine-tune the minimum relatedness for your assistant
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.embeddings:
            return await ctx.send(_("You do not have any embeddings configured!"))
        if not conf.top_n:
            return await ctx.send(_("Top N is set to 0 so no embeddings will be returned"))
        if not await self.can_call_llm(conf, ctx):
            return
        async with ctx.typing():
            query_embedding = await self.request_embedding(query, conf)
            if not query_embedding:
                return await ctx.send(_("Failed to get embedding for your query"))

            embeddings = await asyncio.to_thread(
                conf.get_related_embeddings, ctx.guild.id, query_embedding, relatedness_override=0.1
            )
            if not embeddings:
                return await ctx.send(_("No embeddings could be related to this query with the current settings"))
            for name, em, score, dimension in embeddings:
                for p in pagify(em, page_length=4000):
                    txt = (
                        _("`Entry Name:  `{}\n").format(name)
                        + _("`Relatedness: `{}\n").format(round(score, 4))
                        + _("`Dimensions:  `{}\n").format(dimension)
                    )
                    escaped = escape(p)
                    boxed = box(escaped)
                    txt += boxed
                    embed = discord.Embed(description=txt)
                    await ctx.send(embed=embed)
