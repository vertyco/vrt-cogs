import asyncio
import logging
import re
import sys
import traceback
from datetime import datetime
from inspect import iscoroutinefunction
from io import BytesIO
from multiprocessing import Pool, TimeoutError
from typing import Callable, Dict, List, Optional, Union

import discord
import orjson
import pytz
from openai.error import InvalidRequestError
from redbot.core import bank, version_info
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_number,
    pagify,
)

from .abc import MixinMeta
from .common.utils import (
    compile_messages,
    extract_code_blocks,
    extract_code_blocks_with_lang,
    get_attachments,
    num_tokens_from_string,
    remove_code_blocks,
    request_chat_response,
    request_completion_response,
    request_embedding,
    safe_regex,
    token_cut,
)
from .models import CHAT, MODELS, READ_EXTENSIONS, Conversation, GuildSettings

log = logging.getLogger("red.vrt.assistant.api")


class API(MixinMeta):
    async def handle_message(
        self, message: discord.Message, question: str, conf: GuildSettings, listener: bool = False
    ) -> str:
        outputfile_pattern = r"--outputfile\s+([^\s]+)"
        extract_pattern = r"--extract"
        get_last_message_pattern = r"--last"

        # Extract the optional arguments and their values
        outputfile_match = re.search(outputfile_pattern, question)
        extract_match = re.search(extract_pattern, question)
        get_last_message_match = re.search(get_last_message_pattern, question)

        # Remove the optional arguments from the input string to obtain the question variable
        question = re.sub(outputfile_pattern, "", question)
        question = re.sub(extract_pattern, "", question)
        question = re.sub(get_last_message_pattern, "", question)

        # Check if the optional arguments were present and set the corresponding variables
        outputfile = outputfile_match.group(1) if outputfile_match else None
        extract = bool(extract_match)
        get_last_message = bool(get_last_message_match)

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

        if get_last_message:
            conversation = self.db.get_conversation(
                message.author.id, message.channel.id, message.guild.id
            )
            reply = (
                conversation.messages[-1]["content"]
                if conversation.messages
                else "No message history!"
            )
        else:
            try:
                if conf.use_function_calls:
                    function_calls = self.db.get_function_calls()
                    function_map = self.db.get_function_map()
                else:
                    function_calls = []
                    function_map = {}
                reply = await self.get_chat_response(
                    question,
                    message.author,
                    message.guild,
                    message.channel,
                    conf,
                    function_calls,
                    function_map,
                )
            except InvalidRequestError as e:
                if error := e.error:
                    # OpenAI related error, doesn't need to be restricted to bot owner only
                    await message.reply(error["message"], mention_author=conf.mention)
                    log.error(
                        f"Invalid Request Error (From listener: {listener})\n{error}", exc_info=e
                    )
                else:
                    log.error(f"Invalid Request Error (From listener: {listener})", exc_info=e)
                return
            except KeyError as e:
                await message.channel.send(
                    f"**KeyError in prompt or system message**\n{box(str(e), 'py')}"
                )
                return
            except Exception as e:
                prefix = (await self.bot.get_valid_prefixes(message.guild))[0]
                await message.channel.send(
                    f"Uh oh, something went wrong! Bot owner can use `{prefix}traceback` to view the error."
                )
                log.error(f"API Error (From listener: {listener})", exc_info=e)
                self.bot._last_exception = traceback.format_exc()
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
        embed_perms = message.channel.permissions_for(message.guild.me).embed_links
        file_perms = message.channel.permissions_for(message.guild.me).attach_files
        if files and not file_perms:
            files = []
            content += "\nMissing 'attach files' permissions!"
        delims = ("```", "\n")

        async def send(
            content: Optional[str] = None,
            embed: Optional[discord.Embed] = None,
            embeds: Optional[List[discord.Embed]] = None,
            files: Optional[List[discord.File]] = [],
            mention: bool = False,
        ):
            if reply:
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
            return await message.channel.send(
                content=content, embed=embed, embeds=embeds, files=files
            )

        if len(content) <= 2000:
            await send(content, files=files, mention=conf.mention)
        elif len(content) <= 4000 and embed_perms:
            await send(embed=discord.Embed(description=content), files=files, mention=conf.mention)
        elif embed_perms:
            embeds = [
                discord.Embed(description=p)
                for p in pagify(content, page_length=3900, delims=delims)
            ]
            await send(embeds=embeds, files=files, mention=conf.mention)
        else:
            pages = [p for p in pagify(content, page_length=2000, delims=delims)]
            for index, p in enumerate(pages):
                if index == 0:
                    await send(content=p, files=files, mention=conf.mention)
                else:
                    await send(content=p)

    async def get_chat_response(
        self,
        message: str,
        author: Union[discord.Member, int],
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
        conf: GuildSettings,
        function_calls: Optional[List[dict]] = [],
        function_map: Dict[str, Callable] = {},
    ) -> str:
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

        query_embedding = await request_embedding(text=message, api_key=conf.api_key)
        if not query_embedding:
            log.info(f"Could not get embedding for message: {message}")

        params = {
            "banktype": "global bank" if await bank.is_global() else "local bank",
            "currency": await bank.get_currency_name(guild),
            "bank": await bank.get_bank_name(guild),
            "balance": humanize_number(
                await bank.get_balance(
                    guild.get_member(author) if isinstance(author, int) else author,
                )
            ),
        }
        messages = await asyncio.to_thread(
            self.prepare_messages,
            message,
            guild,
            conf,
            conversation,
            author,
            channel,
            query_embedding,
            params,
        )
        if conf.model in CHAT:
            reply = ""
            calls = 0
            while calls < conf.max_function_calls:
                calls += 1
                response = await request_chat_response(
                    model=conf.model,
                    messages=messages,
                    temperature=conf.temperature,
                    api_key=conf.api_key,
                    functions=function_calls,
                )
                reply = response["content"]
                if function := response.get("function_call"):
                    function_name = function["name"]
                    params = orjson.loads(function.get("arguments", "{}"))
                    if function_name not in function_map:
                        break
                    extras = {
                        "user": guild.get_member(author) if isinstance(author, int) else author,
                        "channel": guild.get_channel_or_thread(channel)
                        if isinstance(channel, int)
                        else channel,
                        "guild": guild,
                        "bot": self.bot,
                        "conf": conf,
                    }
                    kwargs = {**params, **extras}
                    func = function_map[function_name]
                    if iscoroutinefunction(func):
                        result = await func(**kwargs)
                    else:
                        result = await asyncio.to_thread(func, **kwargs)
                    log.info(
                        f"Called function {function_name}\nParams: {params}\nResult: {result}"
                    )
                    conversation.update_messages(result, "function", function_name)
                    messages.append({"role": "function", "name": function_name, "content": result})
                    max_tokens = min(conf.max_tokens, MODELS[conf.model] - 100)
                    while (
                        conversation.conversation_token_count(conf, result) >= max_tokens
                        and messages
                    ):
                        conversation.messages.pop(0)
                        if conf.system_prompt and conf.prompt and len(messages) >= 3:
                            messages.pop(2)
                        elif conf.system_prompt or conf.prompt and len(messages) >= 2:
                            messages.pop(1)
                        else:
                            messages.pop(0)

                else:
                    break
            if calls > 1:
                log.info(f"Made {calls} function calls in a row")
        else:
            max_tokens = min(conf.max_tokens, MODELS[conf.model] - 100)
            compiled = compile_messages(messages)
            cut_message = token_cut(compiled, max_tokens)
            tokens_to_use = round((max_tokens - num_tokens_from_string(cut_message)) * 0.8)
            reply = await request_completion_response(
                model=conf.model,
                message=cut_message,
                temperature=conf.temperature,
                api_key=conf.api_key,
                max_tokens=tokens_to_use,
            )
            for i in ["Assistant:", "assistant:", "System:", "system:", "User:", "user:"]:
                reply = reply.replace(i, "").strip()

        block = False
        for regex in conf.regex_blacklist:
            with Pool(processes=1) as pool:
                try:
                    result = pool.apply_async(safe_regex, (regex, reply))
                    reply = result.get(timeout=2)
                except TimeoutError:
                    log.error(
                        f"Regex {regex} in {guild.name} took too long to process. Skipping..."
                    )
                    if conf.block_failed_regex:
                        block = True
                    continue

        conversation.update_messages(reply, "assistant")
        conversation.cleanup(conf)
        if block:
            reply = "Response failed due to invalid regex, check logs for more info."
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
        params: dict,
    ) -> List[dict]:
        """Prepare content for calling the GPT API

        Args:
            message (str): question or chat message
            guild (discord.Guild): guild associated with the chat
            conf (GuildSettings): config data
            conversation (Conversation): user's conversation object for chat history
            author (Optional[discord.Member]): user chatting with the bot
            channel (Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]]): channel for context
            query_embedding List[float]: message embedding weights

        Returns:
            List[dict]: list of messages prepped for api
        """
        now = datetime.now().astimezone(pytz.timezone(conf.timezone))
        roles = [role for role in author.roles if "everyone" not in role.name] if author else []
        display_name = author.display_name if author else ""

        params = {
            **params,
            "botname": self.bot.user.name,
            "timestamp": f"<t:{round(now.timestamp())}:F>",
            "day": now.strftime("%A"),
            "date": now.strftime("%B %d, %Y"),
            "time": now.strftime("%I:%M %p"),
            "timetz": now.strftime("%I:%M %p %Z"),
            "members": guild.member_count,
            "username": author.name if author else "",
            "user": author.name if author else "",
            "displayname": display_name,
            "datetime": str(datetime.now()),
            "roles": humanize_list([role.name for role in roles]),
            "rolementions": humanize_list([role.mention for role in roles]),
            "avatar": author.display_avatar.url if author else "",
            "owner": guild.owner.name,
            "servercreated": f"<t:{round(guild.created_at.timestamp())}:F>",
            "server": guild.name,
            "messages": len(conversation.messages),
            "tokens": str(conversation.user_token_count(message=message)),
            "retention": str(conf.max_retention),
            "retentiontime": str(conf.max_retention_time),
            "py": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "dpy": discord.__version__,
            "red": str(version_info),
            "cogs": humanize_list([self.bot.get_cog(cog).qualified_name for cog in self.bot.cogs]),
            "channelname": channel.name if channel else "",
            "channelmention": channel.mention if channel else "",
            "topic": channel.topic if channel and isinstance(channel, discord.TextChannel) else "",
        }
        system_prompt = conf.system_prompt.format(**params)
        initial_prompt = conf.prompt.format(**params)

        max_tokens = min(conf.max_tokens, MODELS[conf.model] - 100)

        # Dynamically clean up the conversation to prevent going over token limit
        current_tokens = num_tokens_from_string(system_prompt + initial_prompt + message)
        while (conversation.token_count() + current_tokens) > max_tokens:
            conversation.messages.pop(0)

        total_tokens = conversation.token_count() + current_tokens

        embeddings = []
        for i in conf.get_related_embeddings(query_embedding):
            if (
                num_tokens_from_string(f"\n\nContext:\n{i[1]}\n\n") + total_tokens
                < max_tokens * 0.8
            ):
                embeddings.append(f"{i[1]}")

        if embeddings:
            joined = "\n".join(embeddings)
            prefix = display_name if display_name else "Chat"
            if "{author}" in conf.prompt or "{author}" in conf.system_prompt:
                prefix = "Chat"

            if conf.embed_method == "static":
                message = f"Context:\n{joined}\n\n{prefix}: {message}"

            elif conf.embed_method == "dynamic":
                initial_prompt += f"\n\nContext:\n{joined}"

            elif conf.embed_method == "hybrid" and len(embeddings) > 1:
                initial_prompt += f"\n\nContext:\n{embeddings[1:]}"
                message = f"Context:\n{embeddings[0]}\n\n{prefix}: {message}"

        messages = conversation.prepare_chat(message, system_prompt, initial_prompt)
        return messages
