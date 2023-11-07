import asyncio
import base64
import functools
import json
import logging
import multiprocessing as mp
import re
import traceback
from datetime import datetime
from inspect import iscoroutinefunction
from io import BytesIO
from typing import Callable, Dict, List, Optional, Union

import discord
import pytz
from openai import (
    APIConnectionError,
    AuthenticationError,
    InvalidRequestError,
    RateLimitError,
)
from redbot.core import bank
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number, pagify

from ..abc import MixinMeta
from .constants import (
    READ_EXTENSIONS,
    SUPPORTS_FUNCTIONS,
    SUPPORTS_TOOLS,
    SUPPORTS_VISION,
)
from .models import Conversation, GuildSettings
from .utils import (
    extract_code_blocks,
    extract_code_blocks_with_lang,
    get_attachments,
    get_params,
    process_username,
    remove_code_blocks,
)

log = logging.getLogger("red.vrt.assistant.chathandler")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class ChatHandler(MixinMeta):
    async def handle_message(
        self, message: discord.Message, question: str, conf: GuildSettings, listener: bool = False
    ) -> str:
        outputfile_pattern = r"--outputfile\s+([^\s]+)"
        extract_pattern = r"--extract"
        get_last_message_pattern = r"--last"
        image_url_pattern = r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+\.(?:jpg|jpeg|png|gif|bmp|webp))"

        # Extract the optional arguments and their values
        outputfile_match = re.search(outputfile_pattern, question)
        extract_match = re.search(extract_pattern, question)
        get_last_message_match = re.search(get_last_message_pattern, question)
        image_url_match = re.search(image_url_pattern, question)

        # Remove the optional arguments from the input string to obtain the question variable
        question = re.sub(outputfile_pattern, "", question)
        question = re.sub(extract_pattern, "", question)
        question = re.sub(get_last_message_pattern, "", question)
        question = re.sub(image_url_pattern, "", question)

        # Check if the optional arguments were present and set the corresponding variables
        outputfile = outputfile_match.group(1) if outputfile_match else None
        extract = bool(extract_match)
        get_last_message = bool(get_last_message_match)
        images = []
        if image_url_match:
            for url in image_url_match.groups():
                images.append(url)

        question = question.replace(self.bot.user.mention, self.bot.user.display_name)

        for mention in message.mentions:
            question = question.replace(
                f"<@{mention.id}>",
                f"[Username: {mention.name} | Displayname: {mention.display_name} | Mention: {mention.mention}]",
            )
        for mention in message.channel_mentions:
            question = question.replace(
                f"<#{mention.id}>",
                f"[Channel: {mention.name} | Mention: {mention.mention}]",
            )
        for mention in message.role_mentions:
            mention.__dict__
            question = question.replace(
                f"<@&{mention.id}>",
                f"[Role: {mention.name} | Mention: {mention.mention}]",
            )

        img_ext = ["png", "jpg", "jpeg", "gif", "webp"]
        for i in get_attachments(message):
            has_extension = i.filename.count(".") > 0
            if any(i.filename.lower().endswith(ext) for ext in img_ext):
                image_bytes: bytes = await i.read()
                image_b64 = base64.b64encode(image_bytes).decode()
                images.append(image_b64)
                continue

            if not any(i.filename.lower().endswith(ext) for ext in READ_EXTENSIONS) and has_extension:
                continue

            text = await i.read()

            if isinstance(text, bytes):
                try:
                    text = text.decode()
                except UnicodeDecodeError:
                    pass
                except Exception as e:
                    log.info(f"Failed to decode content of {i.filename}", exc_info=e)

            if i.filename == "message.txt":
                question += f"\n\n### Uploaded File:\n{text}\n"
            else:
                question += f"\n\n### Uploaded File ({i.filename}):\n{text}\n"

        # If referencing a message that isnt part of the user's conversation, include the context
        if hasattr(message, "reference") and message.reference:
            ref = message.reference.resolved
            if ref and ref.author.id != message.author.id:
                # If we're referencing the bot, make sure the bot's message isnt referencing the convo
                include = True
                if hasattr(ref, "reference") and ref.reference:
                    subref = ref.reference.resolved
                    # Make sure the message being referenced isnt just the bot replying
                    if subref and subref.author.id != message.author.id:
                        include = False

                if include:
                    question = (
                        f"{ref.author.name} said: {ref.content}\n\n"
                        f"{message.author.name} replying to {ref.author.name}: {question}"
                    )

        if get_last_message:
            conversation = self.db.get_conversation(message.author.id, message.channel.id, message.guild.id)
            reply = conversation.messages[-1]["content"] if conversation.messages else _("No message history!")
        else:
            try:
                reply = await self.get_chat_response(
                    question,
                    message.author,
                    message.guild,
                    message.channel,
                    conf,
                    message_obj=message,
                    images=images,
                )
            except APIConnectionError as e:
                reply = _("Failed to communicate with endpoint!")
                log.error(f"APIConnectionError (From listener: {listener})", exc_info=e)
            except InvalidRequestError as e:
                if error := e.error:
                    # OpenAI related error, doesn't need to be restricted to bot owner only
                    reply = _("Error: {}").format(error["message"])
                    log.error(
                        f"Invalid Request Error (From listener: {listener})\nERROR: {error}",
                        exc_info=e,
                    )
                else:
                    log.error(f"Invalid Request Error (From listener: {listener})", exc_info=e)
                    return
            except AuthenticationError:
                if message.author == message.guild.owner:
                    reply = _("Invalid API key, please set a new valid key!")
                else:
                    reply = _("Uh oh, looks like my API key is invalid!")
            except RateLimitError as e:
                reply = str(e)
            except KeyError as e:
                log.debug("get_chat_response error", exc_info=e)
                await message.channel.send(_("**KeyError in prompt or system message**\n{}").format(box(str(e), "py")))
                return
            except Exception as e:
                prefix = (await self.bot.get_valid_prefixes(message.guild))[0]
                log.error(f"API Error (From listener: {listener})", exc_info=e)
                self.bot._last_exception = traceback.format_exc()
                reply = _("Uh oh, something went wrong! Bot owner can use `{}` to view the error.").format(
                    f"{prefix}traceback"
                )

        if reply is None:
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

        to_send = [str(i) for i in to_send if str(i).strip()]

        if not to_send and listener:
            return
        elif not to_send and not listener:
            return await message.reply(_("No results found"))

        for index, text in enumerate(to_send):
            if index == 0:
                await self.send_reply(message, text, conf, files, True)
            else:
                await self.send_reply(message, text, conf, None, False)

    async def get_chat_response(
        self,
        message: str,
        author: Union[discord.Member, int],
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
        conf: GuildSettings,
        function_calls: Optional[List[dict]] = None,
        function_map: Optional[Dict[str, Callable]] = None,
        extend_function_calls: bool = True,
        message_obj: Optional[discord.Message] = None,
        images: list[str] = None,
    ) -> str:
        """Call the API asynchronously"""
        if function_calls is None:
            function_calls = []
        if function_map is None:
            function_map = {}

        if conf.use_function_calls and extend_function_calls and conf.model in SUPPORTS_FUNCTIONS:
            # Prepare registry and custom functions
            prepped_function_calls, prepped_function_map = self.db.prep_functions(
                bot=self.bot, conf=conf, registry=self.registry
            )
            function_calls.extend(prepped_function_calls)
            function_map.update(prepped_function_map)

        conversation = self.db.get_conversation(
            member_id=author if isinstance(author, int) else author.id,
            channel_id=channel if isinstance(channel, int) else channel.id,
            guild_id=guild.id,
        )
        if isinstance(author, int):
            author = guild.get_member(author)
        if isinstance(channel, int):
            channel = guild.get_channel(channel)

        query_embedding = []
        user = author if isinstance(author, discord.Member) else None
        message_tokens = await self.count_tokens(message, conf, conf.get_user_model(user))
        words = message.split(" ")
        if conf.top_n and message_tokens < 8191 and len(words) > 5:
            # Save on tokens by only getting embeddings if theyre enabled
            query_embedding = await self.request_embedding(message, conf)

        mem = guild.get_member(author) if isinstance(author, int) else author
        bal = humanize_number(await bank.get_balance(mem)) if mem else _("None")
        extras = {
            "banktype": "global bank" if await bank.is_global() else "local bank",
            "currency": await bank.get_currency_name(guild),
            "bank": await bank.get_bank_name(guild),
            "balance": bal,
        }

        def pop_schema(name: str, calls: List[dict]):
            return [func for func in calls if func["name"] != name]

        # Don't include if user is not a tutor
        not_tutor = [
            author.id not in conf.tutors,
            not any([role.id in conf.tutors for role in author.roles]),
        ]
        if all(not_tutor):
            if "create_memory" in function_map:
                function_calls = pop_schema("create_memory", function_calls)
                del function_map["create_memory"]

        if "edit_memory" in function_map and (not conf.embeddings or all(not_tutor)):
            function_calls = pop_schema("edit_memory", function_calls)
            del function_map["edit_memory"]

        # Don't include if there are no embeddings
        if "search_memories" in function_map and not conf.embeddings:
            function_calls = pop_schema("search_memories", function_calls)
            del function_map["search_memories"]

        max_tokens = self.get_max_tokens(conf, author)
        messages = await self.prepare_messages(
            message,
            guild,
            conf,
            conversation,
            author,
            channel,
            query_embedding,
            extras,
            function_calls,
            images,
        )
        reply = None

        calls = 0
        last_func = None
        repeats = 0
        model = conf.get_user_model(author)
        while True:
            if calls >= conf.max_function_calls:
                function_calls = []

            messages = await self.ensure_supports_vision(messages, conf, author)

            if len(messages) > 1:
                # Iteratively degrade the conversation to ensure it is always under the token limit
                messages, function_calls, degraded = await self.degrade_conversation(
                    messages, function_calls, conf, author
                )
                if degraded:
                    conversation.overwrite(messages)

            if not messages:
                log.error("Messages got pruned too aggressively, increase token limit!")
                break
            try:
                response = await self.request_response(
                    messages=messages,
                    conf=conf,
                    functions=function_calls,
                    member=author,
                )
            except InvalidRequestError as e:
                log.error(
                    f"Invalid request!\n"
                    f"MESSAGES: {json.dumps(messages, indent=2)}\n"
                    f"FUNCTIONS: {json.dumps(function_calls, indent=2) if function_calls else 'None'}",
                    exc_info=e,
                )
                if await self.bot.is_owner(author) and len(function_calls) > 64:
                    dump = json.dumps(function_calls, indent=2)
                    buffer = BytesIO(dump.encode())
                    buffer.name = "FunctionDump.json"
                    buffer.seek(0)
                    file = discord.File(buffer)
                    try:
                        await channel.send(_("Too many functions called"), file=file)
                    except discord.HTTPException:
                        pass
                try:
                    response = await self.request_response(
                        messages=messages,
                        conf=conf,
                        member=author,
                    )
                except InvalidRequestError as e:
                    log.error(
                        f"Invalid request!\nMESSAGES: {json.dumps(messages, indent=2)}",
                        exc_info=e,
                    )
                    raise e
            except Exception as e:
                log.error(
                    f"Response Exception!\n"
                    f"MESSAGES: {json.dumps(messages, indent=2)}\n"
                    f"FUNCTIONS: {json.dumps(function_calls, indent=2) if function_calls else 'None'}",
                    exc_info=e,
                )
                break

            if reply := response["content"]:
                break

            # If content is None then function call must exist
            if model in SUPPORTS_TOOLS:
                response_functions = response.get("tool_calls", [])
            elif response.get("function_call"):
                response_functions = [response["function_call"]]
            else:
                response_functions = None

            if not response_functions:
                continue

            if len(response_functions) > 1:
                log.info(f"Calling {len(response_functions)} functions at once")

            conversation.messages.append(response)
            messages.append(response)

            for function_call in response_functions:
                if model in SUPPORTS_TOOLS:
                    function_name = function_call["function"]["name"]
                    arguments = function_call["function"]["arguments"]
                    tool_id = function_call["id"]
                else:
                    function_name = function_call["name"]
                    arguments = function_call["arguments"]
                    tool_id = None

                calls += 1

                if last_func is None:
                    last_func = function_name
                elif last_func == function_name:
                    repeats += 1
                    if repeats > 4:  # Skip before calling same function a 5th time
                        log.error(f"Too many repeats: {function_name}")
                        function_calls = pop_schema(function_name, function_calls)
                        continue
                else:
                    repeats = 0

                if function_name not in function_map:
                    log.error(f"GPT suggested a function not provided: {function_name}")
                    function_calls = pop_schema(function_name, function_calls)  # Just in case
                    messages.append(
                        {
                            "role": "system",
                            "content": f"{function_name} is not a valid function name",
                        }
                    )
                    continue

                try:
                    params = json.loads(arguments)
                except json.JSONDecodeError:
                    params = {}
                    log.error(f"Failed to parse parameters for custom function {function_name}\nArguments: {arguments}")

                extras = {
                    "user": guild.get_member(author) if isinstance(author, int) else author,
                    "channel": guild.get_channel_or_thread(channel) if isinstance(channel, int) else channel,
                    "guild": guild,
                    "bot": self.bot,
                    "conf": conf,
                }
                kwargs = {**params, **extras}
                func = function_map[function_name]
                try:
                    if iscoroutinefunction(func):
                        func_result = await func(**kwargs)
                    else:
                        func_result = await asyncio.to_thread(func, **kwargs)
                except Exception as e:
                    log.error(
                        f"Custom function {function_name} failed to execute!\nArgs: {arguments}",
                        exc_info=e,
                    )
                    function_calls = pop_schema(function_name, function_calls)
                    continue

                # Prep framework for alternative response types!
                if isinstance(func_result, dict):
                    result = func_result["content"]
                    file = discord.File(
                        BytesIO(func_result["file_bytes"]),
                        filename=func_result["file_name"],
                    )
                    try:
                        await channel.send(file=file)
                    except discord.Forbidden:
                        result = "You do not have permissions to upload files in this channel"
                        function_calls = pop_schema(function_name, function_calls)

                if isinstance(func_result, bytes):
                    result = func_result.decode()
                else:  # Is a string
                    result = str(func_result)

                # Ensure response isnt too large
                result = await self.cut_text_by_tokens(result, conf, max_tokens)
                info = (
                    f"Called function {function_name} in {guild.name} for {author.display_name}\n"
                    f"Params: {params}\nResult: {result}"
                )
                log.info(info)
                role = "tool" if model in SUPPORTS_TOOLS else "function"
                entry = {"role": role, "name": function_name, "content": result}
                if tool_id:
                    entry["tool_call_id"] = tool_id
                messages.append(entry)
                conversation.update_messages(result, role, process_username(function_name), tool_id)
                if message_obj and function_name in ["create_memory", "edit_memory"]:
                    try:
                        await message_obj.add_reaction("\N{BRAIN}")
                    except (discord.Forbidden, discord.NotFound):
                        pass

        # Handle the rest of the reply
        if calls > 1:
            log.info(f"Made {calls} function calls in a row")

        block = False
        if reply:
            for regex in conf.regex_blacklist:
                try:
                    reply = await self.safe_regex(regex, reply)
                except (asyncio.TimeoutError, mp.TimeoutError):
                    log.error(f"Regex {regex} in {guild.name} took too long to process. Skipping...")
                    if conf.block_failed_regex:
                        block = True
                except Exception as e:
                    log.error("Regex sub error", exc_info=e)

            conversation.update_messages(reply, "assistant", process_username(self.bot.user.name))

        if block:
            reply = _("Response failed due to invalid regex, check logs for more info.")

        conversation.cleanup(conf, author)
        conversation.refresh()
        return reply

    async def safe_regex(self, regex: str, content: str):
        process = self.mp_pool.apply_async(
            re.sub,
            args=(
                regex,
                "",
                content,
            ),
        )
        task = functools.partial(process.get, timeout=2)
        loop = asyncio.get_running_loop()
        new_task = loop.run_in_executor(None, task)
        subbed = await asyncio.wait_for(new_task, timeout=5)
        return subbed

    async def prepare_messages(
        self,
        message: str,
        guild: discord.Guild,
        conf: GuildSettings,
        conversation: Conversation,
        author: Optional[discord.Member],
        channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]],
        query_embedding: List[float],
        extras: dict,
        function_calls: List[dict],
        images: list[str] | None,
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
        params = await asyncio.to_thread(get_params, self.bot, guild, now, author, channel, extras)

        def format_string(text: str):
            """Instead of format(**params) possibly giving a KeyError if prompt has code in it"""
            for k, v in params.items():
                key = "{" + k + "}"
                text = text.replace(key, str(v))
            return text

        system_prompt = format_string(conf.system_prompt)
        initial_prompt = format_string(conf.prompt)
        model = conf.get_user_model(author)
        current_tokens = await self.count_tokens(message + system_prompt + initial_prompt, conf, model)
        current_tokens += await self.count_payload_tokens(conversation.messages, conf, model)
        current_tokens += await self.count_function_tokens(function_calls, conf, model)

        max_tokens = self.get_max_tokens(conf, author)

        related = await asyncio.to_thread(conf.get_related_embeddings, query_embedding)

        embeddings = []
        # Get related embeddings (Name, text, score, dimensions)
        for i in related:
            embed_tokens = await self.count_tokens(i[1], conf, model)
            if embed_tokens + current_tokens > max_tokens:
                log.debug("Cannot fit anymore embeddings")
                break
            embeddings.append(i)

        if embeddings:
            results = []
            for embed in embeddings:
                entry = {"memory name": embed[0], "relatedness": embed[2], "content": embed[1]}
                results.append(f"- Embedding: {json.dumps(entry)}")

            role = "function" if function_calls else "user"
            name = "embedding" if function_calls else process_username(author.name) if author else None

            if conf.embed_method == "static":
                conversation.update_messages(results, role, name)

            elif conf.embed_method == "dynamic":
                joined = "\n".join([i[1] for i in results])
                initial_prompt += f"\n\n{joined}"

            else:  # Hybrid embedding
                conversation.update_messages(results[0], role, name)
                if len(embeddings) > 1:
                    joined = "\n".join([i[1] for i in results[1:]])
                    initial_prompt += f"\n\n{joined}"
        images = images if model in SUPPORTS_VISION else []
        messages = conversation.prepare_chat(
            message,
            initial_prompt.strip(),
            system_prompt.strip(),
            name=process_username(author.name) if author else None,
            images=images,
        )
        return messages

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
            content += _("\nMissing 'attach files' permissions!")
        delims = ("```", "\n")

        async def send(
            content: Optional[str] = None,
            embed: Optional[discord.Embed] = None,
            embeds: Optional[List[discord.Embed]] = None,
            files: Optional[List[discord.File]] = None,
            mention: bool = False,
        ):
            if files is None:
                files = []
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
            return await message.channel.send(content=content, embed=embed, embeds=embeds, files=files)

        if len(content) <= 2000:
            await send(content, files=files, mention=conf.mention)
        elif len(content) <= 4000 and embed_perms:
            await send(embed=discord.Embed(description=content), files=files, mention=conf.mention)
        elif embed_perms:
            embeds = [discord.Embed(description=p) for p in pagify(content, page_length=3950, delims=delims)]
            for index, embed in enumerate(embeds):
                if index == 0:
                    await send(embed=embed, files=files, mention=conf.mention)
                else:
                    await send(embed=embed)
        else:
            pages = [p for p in pagify(content, page_length=2000, delims=delims)]
            for index, p in enumerate(pages):
                if index == 0:
                    await send(content=p, files=files, mention=conf.mention)
                else:
                    await send(content=p)
