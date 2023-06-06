import asyncio
import logging
import re
import sys
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Union

import discord
import pytz
from openai.error import InvalidRequestError
from redbot.core import version_info
from redbot.core.utils.chat_formatting import box, humanize_list, pagify

from .abc import MixinMeta
from .common.utils import (
    extract_code_blocks,
    extract_code_blocks_with_lang,
    get_attachments,
    num_tokens_from_string,
    remove_code_blocks,
    request_chat_response,
    request_embedding,
)
from .models import READ_EXTENSIONS, Conversation, GuildSettings

log = logging.getLogger("red.vrt.assistant.api")


class API(MixinMeta):
    async def handle_message(
        self, message: discord.Message, question: str, conf: GuildSettings, listener: bool = False
    ) -> str:
        outputfile_pattern = r"--outputfile\s+([^\s]+)"
        extract_pattern = r"--extract"

        # Extract the optional arguments and their values
        outputfile_match = re.search(outputfile_pattern, question)
        extract_match = re.search(extract_pattern, question)

        # Remove the optional arguments from the input string to obtain the question variable
        question = re.sub(outputfile_pattern, "", question)
        question = re.sub(extract_pattern, "", question)

        # Check if the optional arguments were present and set the corresponding variables
        outputfile = outputfile_match.group(1) if outputfile_match else None
        extract = bool(extract_match)

        for mention in message.mentions:
            question = question.replace(f"<@{mention.id}>", f"@{mention.display_name}")
        for mention in message.channel_mentions:
            question = question.replace(f"<#{mention.id}>", f"#{mention.name}")
        for mention in message.role_mentions:
            question = question.replace(f"<@&{mention.id}>", f"@{mention.name}")
        for i in get_attachments(message):
            has_extension = i.filename.count(".") > 0
            if (
                not any(i.filename.lower().endswith(ext) for ext in READ_EXTENSIONS)
                and has_extension
            ):
                continue
            file_bytes = await i.read()
            if has_extension:
                text = file_bytes.decode()
            else:
                text = file_bytes
            question += f'\n\nUploaded File ({i.filename})\n"""\n{text}\n"""\n'

        try:
            reply = await self.get_chat_response(
                question, message.author, message.guild, message.channel, conf
            )
        except InvalidRequestError as e:
            if error := e.error:
                await message.reply(error["message"], mention_author=conf.mention)
            log.error(f"Invalid Request Error (From listener: {listener})", exc_info=e)
            return
        except Exception as e:
            await message.channel.send(f"**API Error**\n{box(str(e), 'py')}")
            log.error(f"API Error (From listener: {listener})", exc_info=e)
            return

        files = None
        to_send = []
        if outputfile and not extract:
            # Everything to file
            file = discord.File(BytesIO(reply.encode()), filename=outputfile)
            return await message.reply(file=file, mention_author=conf.mention)
        elif outputfile and extract:
            # Code to files and text to discord
            codes = extract_code_blocks(reply)
            files = [
                discord.File(BytesIO(code.encode()), filename=f"{index + 1}_{outputfile}")
                for index, code in enumerate(codes)
            ]
            to_send.append(remove_code_blocks(reply))
        elif not outputfile and extract:
            # Everything to discord but code blocks separated
            codes = [box(code, lang) for lang, code in extract_code_blocks_with_lang(reply)]
            to_send.append(remove_code_blocks(reply))
            to_send.extend(codes)
        else:
            # Everything to discord
            to_send.append(reply)

        for index, text in enumerate(to_send):
            if index == 0:
                await self.send_reply(message, text, conf, files, True)
            else:
                await self.send_reply(message, text, conf, None, False)

    async def send_reply(
        self,
        message: discord.Message,
        content: str,
        conf: GuildSettings,
        files: Optional[List[discord.File]],
        reply: bool = False,
    ):
        if reply:
            if len(content) <= 2000:
                return await message.reply(content, files=files, mention_author=conf.mention)
            elif len(content) <= 4000:
                return await message.reply(
                    embed=discord.Embed(description=content),
                    files=files,
                    mention_author=conf.mention,
                )
            embeds = [
                discord.Embed(description=p)
                for p in pagify(
                    content,
                    page_length=3950,
                    delims=(
                        "```",
                        "\n",
                    ),
                )
            ]
            try:
                await message.reply(embeds=embeds, files=files, mention_author=conf.mention)
            except discord.HTTPException:
                for index, embed in enumerate(embeds):
                    if index == 0:
                        await message.reply(
                            embed=embed,
                            files=files,
                            mention_author=conf.mention,
                        )
                    else:
                        await message.reply(embed=embed, mention_author=conf.mention)
        else:
            if len(content) <= 2000:
                return await message.channel.send(content, files=files)
            elif len(content) <= 4000:
                return await message.channel.send(
                    embed=discord.Embed(description=content), files=files
                )
            embeds = [
                discord.Embed(description=p)
                for p in pagify(
                    content,
                    page_length=3950,
                    delims=(
                        "```",
                        "\n",
                    ),
                )
            ]
            try:
                await message.channel.send(embeds=embeds, files=files)
            except discord.HTTPException:
                for index, embed in enumerate(embeds):
                    if index == 0:
                        await message.channel.send(
                            embed=embed,
                            files=files,
                        )
                    else:
                        await message.channel.send(embed=embed)

    async def get_chat_response(
        self,
        message: str,
        author: Union[discord.Member, int],
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
        conf: GuildSettings,
    ):
        """Call the API asynchronously"""
        conversation = self.db.get_conversation(
            author if isinstance(author, int) else author.id,
            channel if isinstance(channel, int) else channel.id,
            guild.id,
        )
        conversation.cleanup(conf)
        if isinstance(author, int):
            author = guild.get_member(author)
        if isinstance(channel, int):
            channel = guild.get_channel(channel)
        try:
            query_embedding = await request_embedding(text=message, api_key=conf.api_key)
            if not query_embedding:
                log.info(f"Could not get embedding for message: {message}")
            messages = await asyncio.to_thread(
                self.prepare_messages,
                message,
                guild,
                conf,
                conversation,
                author,
                channel,
                query_embedding,
            )
            reply = await request_chat_response(
                model=conf.model,
                messages=messages,
                temperature=conf.temperature,
                api_key=conf.api_key,
            )
            for regex in conf.regex_blacklist:
                reply = re.sub(regex, "", reply).strip()
            conversation.update_messages(reply, "assistant")
        finally:
            conversation.cleanup(conf)
        return reply

    def prepare_messages(
        self,
        message: str,
        guild: discord.Guild,
        conf: GuildSettings,
        conversation: Conversation,
        author: Optional[discord.Member],
        channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]],
        query_embedding: List[float],
    ) -> str:
        """Prepare content for calling the GPT API

        Args:
            message (str): question or chat message
            guild (discord.Guild): guild associated with the chat
            conf (GuildSettings): config data
            conversation (Conversation): user's conversation object for chat history
            author (Optional[discord.Member]): user chatting with the bot
            channel (Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]]): channel for context

        Returns:
            str: the response from ChatGPT
        """
        now = datetime.now().astimezone(pytz.timezone(conf.timezone))

        params = {
            "botname": self.bot.user.name,
            "timestamp": f"<t:{round(now.timestamp())}:F>",
            "day": now.strftime("%A"),
            "date": now.strftime("%B %d, %Y"),
            "time": now.strftime("%I:%M %p"),
            "timetz": now.strftime("%I:%M %p %Z"),
            "members": guild.member_count,
            "username": author.name if author else "",
            "user": author.display_name if author else "",
            "datetime": str(datetime.now()),
            "roles": humanize_list([role.name for role in author.roles]) if author else "",
            "avatar": author.display_avatar.url if author else "",
            "owner": guild.owner,
            "servercreated": f"<t:{round(guild.created_at.timestamp())}:F>",
            "server": guild.name,
            "messages": len(conversation.messages),
            "tokens": conversation.user_token_count(message=message),
            "retention": conf.max_retention,
            "retentiontime": conf.max_retention_time,
            "py": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "dpy": discord.__version__,
            "red": version_info,
            "cogs": humanize_list([self.bot.get_cog(cog).qualified_name for cog in self.bot.cogs]),
            "channelname": channel.name if channel else "",
            "channelmention": channel.mention if channel else "",
            "topic": channel.topic if channel and isinstance(channel, discord.TextChannel) else "",
        }
        system_prompt = conf.system_prompt.format(**params)
        initial_prompt = conf.prompt.format(**params)

        # Dynamically clean up the conversation to prevent going over token limit
        prompt_tokens = num_tokens_from_string(system_prompt + initial_prompt)
        while (conversation.token_count() + prompt_tokens) > conf.max_tokens * 0.85:
            conversation.messages.pop(0)

        total_tokens = conversation.token_count() + prompt_tokens + num_tokens_from_string(message)

        embeddings = []
        for i in conf.get_related_embeddings(query_embedding):
            if (
                num_tokens_from_string(f"\n\nContext:\n{i[1]}\n\n") + total_tokens
                < conf.max_tokens * 0.8
            ):
                embeddings.append(f"{i[1]}")

        if embeddings:
            joined = "\n".join(embeddings)

            if conf.embed_method == "static":
                message = f"{joined}\n\nChat: {message}"

            elif conf.embed_method == "dynamic":
                initial_prompt += f"\n\nContext:\n{joined}"

            elif conf.embed_method == "hybrid" and len(embeddings) > 1:
                initial_prompt += f"\n\nContext:\n{embeddings[1:]}"
                message = f"{embeddings[0]}\n\nChat: {message}"

        conversation.update_messages(message, "user")
        messages = conversation.prepare_chat(system_prompt, initial_prompt)
        return messages
