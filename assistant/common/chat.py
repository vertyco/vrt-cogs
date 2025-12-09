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
from io import BytesIO, StringIO
from typing import Callable, Dict, List, Optional, Union

import discord
import httpx
import openai
import pytz
from openai.types.chat.chat_completion_message import (
    ChatCompletionMessage,
    FunctionCall,
)
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
)
from redbot.core import bank
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number, text_to_file
from sentry_sdk import add_breadcrumb

from ..abc import MixinMeta
from .constants import DO_NOT_RESPOND_SCHEMA, READ_EXTENSIONS, SUPPORTS_VISION
from .models import Conversation, GuildSettings
from .reply import send_reply
from .utils import (
    clean_name,
    clean_response,
    clean_responses,
    ensure_message_compatibility,
    ensure_supports_vision,
    ensure_tool_consistency,
    extract_code_blocks,
    extract_code_blocks_with_lang,
    get_attachments,
    get_params,
    purge_images,
    remove_code_blocks,
    is_core_tool,
)

log = logging.getLogger("red.vrt.assistant.chathandler")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class ChatHandler(MixinMeta):
    async def handle_message(
        self,
        message: discord.Message,
        question: str,
        conf: GuildSettings,
        listener: bool = False,
        model_override: Optional[str] = None,
        auto_answer: Optional[bool] = False,
        trigger_prompt: Optional[str] = None,
        **kwargs,
    ):
        outputfile_pattern = r"--outputfile\s+([^\s]+)"
        extract_pattern = r"--extract"
        get_last_message_pattern = r"--last"
        image_url_pattern = r"(https?:\/\/\S+\.(?:png|gif|webp|jpg|jpeg)\b)"

        # Extract the optional arguments and their values
        outputfile_match = re.search(outputfile_pattern, question)
        extract_match = re.search(extract_pattern, question)
        get_last_message_match = re.search(get_last_message_pattern, question)
        image_url_match = re.findall(image_url_pattern, question)

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
            for url in image_url_match:
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
            question = question.replace(
                f"<@&{mention.id}>",
                f"[Role: {mention.name} | Mention: {mention.mention}]",
            )

        img_ext = ["png", "jpg", "jpeg", "webp"]
        for i in get_attachments(message):
            has_extension = i.filename.count(".") > 0
            if any(i.filename.lower().endswith(ext) for ext in img_ext):
                # No reason to download the image now, we can just use the url
                image_bytes: bytes = await i.read()
                image_b64 = base64.b64encode(image_bytes).decode()
                image_format = i.filename.split(".")[-1].lower()
                image_string = f"data:image/{image_format};base64,{image_b64}"
                images.append(image_string)
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
                    log.error(f"Failed to decode content of {i.filename}", exc_info=e)

            if i.filename == "message.txt":
                question += f"\n\n### Uploaded File:\n{text}\n"
            else:
                question += f"\n\n### Uploaded File ({i.filename}):\n{text}\n"

        if conf.collab_convos:
            mem_id = message.channel.id
            if message.author.name == message.author.display_name:
                question = f"@{message.author.name}: {question}"
            else:
                question = f"@{message.author.name}({message.author.display_name}): {question}"
        else:
            mem_id = message.author.id

        conversation = self.db.get_conversation(mem_id, message.channel.id, message.guild.id)

        # If referencing a message that isnt part of the user's conversation, include the context
        if hasattr(message, "reference") and message.reference:
            ref = message.reference.resolved
            if ref and ref.author.id != message.author.id and ref.author.id != self.bot.user.id:
                # If we're referencing the bot, make sure the bot's message isnt referencing the convo
                include = True
                if hasattr(ref, "reference") and ref.reference:
                    subref = ref.reference.resolved
                    # Make sure the message being referenced isnt just the bot replying
                    if subref and subref.author.id != message.author.id:
                        include = False

                if include:
                    ref_author: discord.User | discord.Member = ref.author
                    if ref_author.display_name == ref_author.name:
                        name = f"@{ref_author.name}"
                    else:
                        name = f"@{ref_author.name}({ref_author.display_name})"
                    question = f"{name}: {ref.content}\n\n# REPLY\n{question}"

        if get_last_message:
            reply = conversation.messages[-1]["content"] if conversation.messages else _("No message history!")
        else:
            try:
                reply = await self.get_chat_response(
                    message=question,
                    author=message.author,
                    guild=message.guild,
                    channel=message.channel,
                    conf=conf,
                    message_obj=message,
                    images=images,
                    model_override=model_override,
                    auto_answer=auto_answer,
                    trigger_prompt=trigger_prompt,
                )
            except openai.InternalServerError as e:
                if e.body and isinstance(e.body, dict):
                    if msg := e.body.get("message"):
                        log.warning("InternalServerError [message]", exc_info=e)
                        reply = _("Internal Server Error({}): {}").format(e.status_code, msg)
                    else:
                        log.error(f"Internal Server Error (From listener: {listener})", exc_info=e)
                        reply = _("Internal Server Error({}): {}").format(e.status_code, e.body)
                else:
                    reply = _("Internal Server Error({}): {}").format(e.status_code, e.message)
            except openai.APIConnectionError as e:
                reply = _("Failed to communicate with API!")
                log.error(f"APIConnectionError (From listener: {listener})", exc_info=e)
            except openai.AuthenticationError:
                if message.author == message.guild.owner:
                    reply = _("Invalid API key, please set a new valid key!")
                else:
                    reply = _("Uh oh, looks like my API key is invalid!")
            except openai.RateLimitError as e:
                reply = _("Rate limit error: {}").format(e.message)
            except httpx.ReadTimeout as e:
                reply = _("Read timeout error: {}").format(str(e))
            except Exception as e:
                prefix = (await self.bot.get_valid_prefixes(message.guild))[0]
                log.error(f"API Error (From listener: {listener})", exc_info=e)
                status = await self.openai_status()
                self.bot._last_exception = f"{traceback.format_exc()}\nAPI Status: {status}"
                reply = _("Uh oh, something went wrong! Bot owner can use `{}` to view the error.").format(
                    f"{prefix}traceback"
                )
                reply += "\n\n" + _("API Status: {}").format(status)

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
                await send_reply(
                    message=message,
                    content=text,
                    conf=conf,
                    files=files,
                    reply=True,
                )
            else:
                await send_reply(message=message, content=text, conf=conf)

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
        model_override: Optional[str] = None,
        auto_answer: Optional[bool] = False,
        trigger_prompt: Optional[str] = None,
    ) -> Union[str, None]:
        """Call the API asynchronously"""
        functions = function_calls.copy() if function_calls else []
        mapping = function_map.copy() if function_map else {}

        async def do_not_respond(*args, **kwargs):
            return {"return_null": True, "content": "do_not_respond"}

        if conf.use_function_calls and extend_function_calls:
            # Prepare registry and custom functions
            prepped_function_calls, prepped_function_map = await self.db.prep_functions(
                bot=self.bot, conf=conf, registry=self.registry, member=author
            )
            functions.extend(prepped_function_calls)
            mapping.update(prepped_function_map)
            if auto_answer:
                functions.append(DO_NOT_RESPOND_SCHEMA)
                mapping["do_not_respond"] = do_not_respond

        if not conf.use_function_calls and functions:
            functions = []

        mem_id = author if isinstance(author, int) else author.id
        chan_id = channel if isinstance(channel, int) else channel.id
        if conf.collab_convos:
            mem_id = chan_id
        conversation = self.db.get_conversation(
            member_id=mem_id,
            channel_id=chan_id,
            guild_id=guild.id,
        )

        conversation.cleanup(conf, author)
        conversation.refresh()
        try:
            return await self._get_chat_response(
                message=message,
                author=author,
                guild=guild,
                channel=channel,
                conf=conf,
                conversation=conversation,
                function_calls=functions,
                function_map=mapping,
                message_obj=message_obj,
                images=images,
                model_override=model_override,
                auto_answer=auto_answer,
                trigger_prompt=trigger_prompt,
            )
        finally:
            conversation.cleanup(conf, author)
            conversation.refresh()

    async def _get_chat_response(
        self,
        message: str,
        author: Union[discord.Member, int],
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
        conf: GuildSettings,
        conversation: Conversation,
        function_calls: List[dict],
        function_map: Dict[str, Callable],
        message_obj: Optional[discord.Message] = None,
        images: list[str] = None,
        model_override: Optional[str] = None,
        auto_answer: Optional[bool] = False,
        trigger_prompt: Optional[str] = None,
    ) -> Union[str, None]:
        if isinstance(author, int):
            author = guild.get_member(author)
        if isinstance(channel, int):
            channel = guild.get_channel(channel)

        query_embedding = []
        user = author if isinstance(author, discord.Member) else guild.get_member(author)
        user_id = author.id if isinstance(author, discord.Member) else author
        model = conf.get_chat_model(self.db.endpoint_override, user)
        using_ollama_endpoint = bool(self.db.endpoint_override)

        # Ensure the message is not longer than 1048576 characters
        message = message[:1048576]

        # Determine if we should embed the user's message
        message_tokens = await self.count_tokens(message, model)
        words = message.split(" ")
        get_embed_conditions = [
            conf.embeddings,  # We actually have embeddings to compare with
            len(words) > 1,  # Message is long enough
            conf.top_n,  # Top n is greater than 0
            message_tokens < 8191,
        ]
        if all(get_embed_conditions):
            if conf.question_mode:
                # If question mode is enabled, only the first message and messages that end with a ? will be embedded
                if message.endswith("?") or not conversation.messages:
                    query_embedding = await self.request_embedding(message, conf)
            else:
                query_embedding = await self.request_embedding(message, conf)

        log.debug(f"Query embedding: {len(query_embedding)}")

        mem = guild.get_member(author) if isinstance(author, int) else author
        bal = humanize_number(await bank.get_balance(mem)) if mem else _("None")
        extras = {
            "banktype": "global bank" if await bank.is_global() else "local bank",
            "currency": await bank.get_currency_name(guild),
            "bank": await bank.get_bank_name(guild),
            "balance": bal,
        }

        if using_ollama_endpoint and function_calls:
            function_calls = [i for i in function_calls if is_core_tool(i.get("name", ""))]
            function_map = {k: v for k, v in function_map.items() if is_core_tool(k)}
            log.debug(f"Filtered to {len(function_calls)} core tools for Ollama endpoint")

        # Function availability filters apply regardless of the endpoint type
        # Don't include if user is not a tutor
        not_tutor = [
            user_id not in conf.tutors,
            not any([role.id in conf.tutors for role in user.roles]),
        ]

        if "create_memory" in function_map and all(not_tutor):
            function_calls = [i for i in function_calls if i["name"] != "create_memory"]
            del function_map["create_memory"]

        if "edit_memory" in function_map and (not conf.embeddings or all(not_tutor)):
            function_calls = [i for i in function_calls if i["name"] != "edit_memory"]
            del function_map["edit_memory"]

        # Don't include if there are no embeddings
        if "search_memories" in function_map and not conf.embeddings:
            function_calls = [i for i in function_calls if i["name"] != "search_memories"]
            del function_map["search_memories"]
        if "list_memories" in function_map and not conf.embeddings:
            function_calls = [i for i in function_calls if i["name"] != "list_memories"]
            del function_map["list_memories"]

        if "search_web_brave" in function_map and not self.db.brave_api_key:
            function_calls = [i for i in function_calls if i["name"] != "search_web_brave"]
            del function_map["search_web_brave"]

        if "edit_image" in function_map and (not conversation.get_images() and not images):
            function_calls = [i for i in function_calls if i["name"] != "edit_image"]
            del function_map["edit_image"]

        if self.db.endpoint_override:
            # Redundant with core tool filtering for Ollama; explicitly skips image tools when overriding endpoints
            for func in ("generate_image", "edit_image"):
                if func in function_map:
                    function_calls = [i for i in function_calls if i["name"] != func]
                    del function_map[func]

        messages = await self.prepare_messages(
            message=message,
            guild=guild,
            conf=conf,
            conversation=conversation,
            author=author,
            channel=channel,
            query_embedding=query_embedding,
            extras=extras,
            function_calls=function_calls,
            images=images,
            auto_answer=auto_answer,
            trigger_prompt=trigger_prompt,
        )
        reply = None

        calls = 0
        tries = 0
        while True:
            if tries > 2:
                log.error("breaking after 3 tries, purge_images function must have failed")
                break
            if calls >= conf.max_function_calls:
                function_calls = []

            await ensure_supports_vision(messages, conf, author, self.db.endpoint_override)
            await ensure_message_compatibility(messages, conf, author, self.db.endpoint_override)
            if self.db.endpoint_override:
                # Replace "developer" role with "system" role
                for i in messages:
                    if i["role"] == "developer":
                        i["role"] = "system"

            # Iteratively degrade the conversation to ensure it is always under the token limit
            degraded = await self.degrade_conversation(messages, function_calls, conf, author)

            before = len(messages)
            cleaned = await ensure_tool_consistency(messages)
            if cleaned and before == len(messages):
                log.error("Something went wrong while ensuring tool call consistency")

            await clean_responses(messages)

            if cleaned or degraded:
                conversation.overwrite(messages)

            if not messages:
                log.error("Messages got pruned too aggressively, increase token limit!")
                break
            try:
                response: ChatCompletionMessage = await self.request_response(
                    messages=messages,
                    conf=conf,
                    functions=function_calls,
                    member=author,
                    model_override=model_override,
                )
            except httpx.ReadTimeout:
                reply = _("Request timed out, please try again.")
                break
            except openai.BadRequestError as e:
                if "Invalid image" in str(e):
                    await purge_images(messages)
                    tries += 1
                    continue

                if e.body and isinstance(e.body, dict):
                    msg = e.body.get("message", f"Unknown error: {str(e)}")
                    log.error("BadRequestError2 [message]", exc_info=e)
                    reply = _("Bad Request Error2({}): {}").format(e.status_code, msg)
                else:
                    reply = _("Bad Request Error({}): {}").format(e.status_code, e.message)
                if guild.id == 625757527765811240:
                    # Dump payload for debugging if its my guild
                    dump_file = text_to_file(json.dumps(messages, indent=2), filename=f"{author}_convo_BadRequest.json")
                    await channel.send(file=dump_file)
                break
            except Exception as e:
                add_breadcrumb(
                    category="chat",
                    message=f"Response Exception: {model}",
                    level="info",
                )
                if guild.id == 625757527765811240:
                    # Dump payload for debugging if its my guild
                    dump_file = text_to_file(json.dumps(messages, indent=2), filename=f"{author}_convo_Exception.json")
                    await channel.send(file=dump_file)

                raise e

            if reply := response.content:
                break

            await clean_response(response)

            if response.tool_calls:
                log.debug("Tool calls detected")
                response_functions: list[ChatCompletionMessageToolCall] = response.tool_calls
            elif response.function_call:
                log.debug("Function call detected")
                response_functions: list[FunctionCall] = [response.function_call]
            else:
                log.error("No reply and no function calls???")
                continue

            if using_ollama_endpoint:
                log.debug(f"Processing {len(response_functions)} Ollama tool calls")

            if len(response_functions) > 1:
                log.debug(f"Calling {len(response_functions)} functions at once")

            dump = response.model_dump()
            if not dump["function_call"]:
                del dump["function_call"]
            if not dump["tool_calls"]:
                del dump["tool_calls"]

            conversation.messages.append(dump)
            messages.append(dump)

            # Add function call count
            conf.functions_called += len(response_functions)

            for function_call in response_functions:
                if hasattr(function_call, "name") and hasattr(function_call, "arguments"):
                    # This is a FunctionCall
                    function_name = function_call.name
                    arguments = function_call.arguments
                    tool_id = None
                    role = "tool"
                elif hasattr(function_call, "function") and hasattr(function_call, "id"):
                    # This is a ChatCompletionMessageToolCall
                    function_name = function_call.function.name
                    arguments = function_call.function.arguments
                    tool_id = function_call.id
                    role = "tool"
                else:
                    log.error(f"Unknown function call type: {type(function_call)}: {function_call}")
                    # Try to handle as ChatCompletionMessageToolCall as fallback
                    function_name = function_call.function.name
                    arguments = function_call.function.arguments
                    tool_id = function_call.id
                    role = "tool"

                calls += 1

                if function_name not in function_map:
                    log.error(f"GPT suggested a function not provided: {function_name}")
                    e = {
                        "role": role,
                        "name": "invalid_function",
                        "content": f"{function_name} is not a valid function name",
                    }
                    if tool_id:
                        e["tool_call_id"] = tool_id
                    messages.append(e)
                    conversation.messages.append(e)
                    # Remove the function call from the list
                    function_calls = [i for i in function_calls if i["name"] != function_name]
                    continue

                if arguments != "{}":
                    try:
                        args = json.loads(arguments)
                        parse_success = True
                    except json.JSONDecodeError:
                        args = {}
                        parse_success = False
                else:
                    args = {}
                    parse_success = True

                if using_ollama_endpoint and not parse_success:
                    log.warning(f"Ollama tool call argument parsing failed for {function_name}: {arguments}")

                if parse_success:
                    data = {
                        **extras,
                        "user": guild.get_member(author) if isinstance(author, int) else author,
                        "channel": guild.get_channel_or_thread(channel) if isinstance(channel, int) else channel,
                        "guild": guild,
                        "bot": self.bot,
                        "conf": conf,
                        "conversation": conversation,
                        "messages": messages,
                        "message_obj": message_obj,
                    }
                    kwargs = {**args, **data}
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
                        func_result = traceback.format_exc()
                        function_calls = [i for i in function_calls if i["name"] != function_name]
                else:
                    # Help the model self-correct
                    func_result = f"JSONDecodeError: Failed to parse arguments for function {function_name}"

                return_null = False

                if isinstance(func_result, discord.Embed):
                    content = func_result.description or _("Result sent!")
                    try:
                        await channel.send(embed=func_result)
                    except discord.Forbidden:
                        content = "You do not have permissions to embed links in this channel"
                        function_calls = [i for i in function_calls if i["name"] != function_name]
                elif isinstance(func_result, discord.File):
                    content = "File uploaded!"
                    try:
                        await channel.send(file=func_result)
                    except discord.Forbidden:
                        content = "You do not have permissions to upload files in this channel"
                        function_calls = [i for i in function_calls if i["name"] != function_name]
                elif isinstance(func_result, dict):
                    # For complex responses
                    content = func_result.get("result_text")
                    if not content:
                        content = func_result.get("content")
                    return_null = func_result.get("return_null", False)
                    kwargs = {}
                    if "embed" in func_result and channel.permissions_for(guild.me).embed_links:
                        if not isinstance(func_result["embed"], discord.Embed):
                            raise TypeError("Embed must be a discord.Embed object")
                        kwargs["embed"] = func_result["embed"]
                    if "file" in func_result and channel.permissions_for(guild.me).attach_files:
                        if not isinstance(func_result["file"], discord.File):
                            raise TypeError("File must be a discord.File object")
                        kwargs["file"] = func_result["file"]
                    if "embeds" in func_result and channel.permissions_for(guild.me).embed_links:
                        if not isinstance(func_result["embeds"], list):
                            raise TypeError("Embeds must be a list of discord.Embed objects")
                        if not all(isinstance(i, discord.Embed) for i in func_result["embeds"]):
                            raise TypeError("Embeds must be a list of discord.Embed objects")
                        kwargs["embeds"] = func_result["embeds"]
                    if "files" in func_result and channel.permissions_for(guild.me).attach_files:
                        if not isinstance(func_result["files"], list):
                            raise TypeError("Files must be a list of discord.File objects")
                        if not all(isinstance(i, discord.File) for i in func_result["files"]):
                            raise TypeError("Files must be a list of discord.File objects")
                        kwargs["files"] = func_result["files"]
                    if kwargs:
                        try:
                            await channel.send(**kwargs)
                        except discord.HTTPException as e:
                            content = f"discord.HTTPException: {e.text}"
                            function_calls = [i for i in function_calls if i["name"] != function_name]

                elif isinstance(func_result, bytes):
                    content = func_result.decode()
                elif isinstance(func_result, str):
                    content = str(func_result)
                else:
                    log.error(f"Function {function_name} returned an unknown type: {type(func_result)}")
                    content = f"Unknown type: {type(func_result)}"

                logging_content = StringIO()
                if isinstance(func_result, str) and len(func_result):
                    logging_content.write(func_result[:2000])
                elif isinstance(func_result, bytes):
                    logging_content.write(str(func_result)[:20] + "... (bytes content)")
                elif isinstance(func_result, dict):
                    for k, v in func_result.items():
                        txt = str(v)
                        if txt.startswith("data:image/"):
                            txt = txt[:20] + "... (image content)"

                        logging_content.write(f"{k}: {txt[:1000]}\n")

                info = (
                    f"Called function {function_name} in {guild.name} for {author.display_name}\n"
                    f"Params: {args}\nResult: {logging_content.getvalue()}"
                )
                log.debug(info)
                if isinstance(content, str):
                    # Ensure response isnt too large
                    content = await self.cut_text_by_tokens(content, conf, author)

                e = {"role": role, "name": function_name, "content": content}
                if tool_id:
                    e["tool_call_id"] = tool_id
                messages.append(e)
                conversation.messages.append(e)

                if return_null:
                    return None

                if message_obj and function_name in ["create_memory", "edit_memory"]:
                    try:
                        await message_obj.add_reaction("\N{BRAIN}")
                    except (discord.Forbidden, discord.NotFound):
                        pass

        # Handle the rest of the reply
        if calls > 1:
            log.debug(f"Made {calls} function calls in a row")

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

            conversation.update_messages(reply, "assistant", clean_name(self.bot.user.name))

        if block:
            reply = _("Response failed due to invalid regex, check logs for more info.")

        if reply and reply == "do_not_respond":
            log.info("Auto answer triggered, not responding to user")
            return None

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
        auto_answer: Optional[bool] = False,
        trigger_prompt: Optional[str] = None,
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
            extras (dict): extra parameters to include in the prompt
            function_calls (List[dict]): list of function calls to include in the prompt
            images (list[str] | None): list of image URLs to include in the prompt
            auto_answer (Optional[bool]): whether this is an auto answer response
            trigger_prompt (Optional[str]): custom prompt to use when triggered by keywords

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

        if channel.id in conf.channel_prompts:
            system_prompt = format_string(conf.channel_prompts[channel.id])
        else:
            system_prompt = format_string(conversation.system_prompt_override or conf.system_prompt)

        initial_prompt = format_string(conf.prompt)
        model = conf.get_chat_model(self.db.endpoint_override, author)
        current_tokens = await self.count_tokens(message + system_prompt + initial_prompt, model)
        current_tokens += await self.count_payload_tokens(conversation.messages, model)
        current_tokens += await self.count_function_tokens(function_calls, model)

        max_tokens = self.get_max_tokens(conf, author)

        related = await asyncio.to_thread(conf.get_related_embeddings, guild.id, query_embedding)

        embeds: List[str] = []
        # Get related embeddings (Name, text, score, dimensions)
        for i in related:
            embed_tokens = await self.count_tokens(i[1], model)
            if embed_tokens + current_tokens > max_tokens:
                log.debug("Cannot fit anymore embeddings")
                break
            embeds.append(f"[{i[0]}](Relatedness: {round(i[2], 4)}): {i[1]}\n")

        if embeds:
            if conf.embed_method == "static":
                # Ebeddings go directly into the user message
                message += f"\n\n# RELATED EMBEDDINGS\n{''.join(embeds)}"
            elif conf.embed_method == "dynamic":
                # Embeddings go into the system prompt
                system_prompt += f"\n\n# RELATED EMBEDDINGS\n{''.join(embeds)}"
            elif conf.embed_method == "user":
                # Embeddings get injected into the initial user message
                initial_prompt += f"\n\n# RELATED EMBEDDINGS\n{''.join(embeds)}"
            else:  # Hybrid, first embed goes into user message, rest go into system prompt
                message += f"\n\n# RELATED EMBEDDINGS\n{embeds[0]}"
                if len(embeds) > 1:
                    system_prompt += f"\n\n# RELATED EMBEDDINGS\n{''.join(embeds[1:])}"

        if auto_answer:
            initial_prompt += (
                "\n# AUTO ANSWER:\nYou are responding to a triggered event not specifically requested by the user. "
                "You may opt to not respond if necessary by calling the `do_not_respond` function.\n"
                "If you do not have access to functions, you may respond with the exact phrase `do_not_respond`"
            )

        if trigger_prompt:
            formatted_trigger = format_string(trigger_prompt)
            initial_prompt += f"\n# TRIGGER RESPONSE:\n{formatted_trigger}"

        images = images if model in SUPPORTS_VISION else []
        messages = conversation.prepare_chat(
            message,
            initial_prompt.strip(),
            system_prompt.strip(),
            name=clean_name(author.name) if author else None,
            images=images,
            resolution=conf.vision_detail,
        )
        return messages
