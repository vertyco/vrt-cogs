import asyncio
import base64
import functools
import logging
import multiprocessing as mp
import re
import traceback
from contextlib import suppress
from datetime import datetime
from inspect import Parameter, iscoroutinefunction, signature
from io import BytesIO, StringIO
from typing import Callable, Dict, List, Optional, Union

import discord
import httpx
import openai
import orjson
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
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_number,
    text_to_file,
)
from sentry_sdk import add_breadcrumb

from ..abc import MixinMeta
from ..views import AdminToolApprovalView
from .constants import (
    DO_NOT_RESPOND_SCHEMA,
    IMAGE_RETAIN_TURNS,
    MODELS,
    READ_EXTENSIONS,
    TOOL_RESULT_HARD_CLEAR_PLACEHOLDER,
    TOOL_RESULT_HARD_RATIO,
    TOOL_RESULT_MAX_CONTEXT_SHARE,
    TOOL_RESULT_PROTECT_RECENT,
    TOOL_RESULT_SOFT_MIN_CHARS,
    TOOL_RESULT_SOFT_RATIO,
    TOOL_RESULT_SOFT_TRIM_HEAD,
    TOOL_RESULT_SOFT_TRIM_MAX,
    TOOL_RESULT_SOFT_TRIM_TAIL,
)
from .models import Conversation, GuildSettings, render_tool_category
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
    extract_document_text,
    get_attachments,
    get_params,
    is_document,
    purge_images,
    remove_code_blocks,
)

log = logging.getLogger("red.vrt.assistant.chathandler")
_ = Translator("Assistant", __file__)


def append_reasoning_block(reply: Optional[str], reasoning: Optional[str], conf: GuildSettings) -> Optional[str]:
    if not reply or not reasoning:
        return reply
    if not conf.think_tag_prefix or not conf.think_tag_suffix:
        return reply
    return f"{reply}\n{conf.think_tag_prefix}{reasoning.strip()}{conf.think_tag_suffix}"


def prune_old_tool_results(messages: list[dict], context_fill_ratio: float = 0.0) -> None:
    """Two-tier pruning of old tool/function results to save context window space.

    Tier 1 (soft-trim): when *context_fill_ratio* >= ``TOOL_RESULT_SOFT_RATIO``,
    oversized results are truncated to head + tail with a note.

    Tier 2 (hard-clear): when *context_fill_ratio* >= ``TOOL_RESULT_HARD_RATIO``,
    old results are replaced entirely with a short placeholder.

    Recent results (within the last ``TOOL_RESULT_PROTECT_RECENT`` messages) are
    always left intact.
    """
    if len(messages) <= TOOL_RESULT_PROTECT_RECENT:
        return

    cutoff = len(messages) - TOOL_RESULT_PROTECT_RECENT
    for msg in messages[:cutoff]:
        if msg.get("role") not in ("tool", "function"):
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue

        # Tier 2 — hard-clear when context pressure is high
        if context_fill_ratio >= TOOL_RESULT_HARD_RATIO and len(content) > TOOL_RESULT_SOFT_MIN_CHARS:
            msg["content"] = TOOL_RESULT_HARD_CLEAR_PLACEHOLDER
            continue

        # Tier 1 — soft-trim when context pressure is moderate
        if context_fill_ratio >= TOOL_RESULT_SOFT_RATIO and len(content) > TOOL_RESULT_SOFT_MIN_CHARS:
            head = content[:TOOL_RESULT_SOFT_TRIM_HEAD]
            tail = content[-TOOL_RESULT_SOFT_TRIM_TAIL:]
            trimmed = len(content) - TOOL_RESULT_SOFT_TRIM_MAX
            msg["content"] = head + f"\n... [trimmed {trimmed} chars] ...\n" + tail
            continue

        # Fallback: always soft-trim truly huge results even at low context pressure
        if len(content) > TOOL_RESULT_SOFT_TRIM_MAX * 4:
            head = content[:TOOL_RESULT_SOFT_TRIM_HEAD]
            tail = content[-TOOL_RESULT_SOFT_TRIM_TAIL:]
            trimmed = len(content) - TOOL_RESULT_SOFT_TRIM_MAX
            msg["content"] = head + f"\n... [trimmed {trimmed} chars] ...\n" + tail


def evict_old_images(messages: list[dict]) -> bool:
    """Remove images from messages once the model has responded enough times.

    Images are the most token-expensive content in a conversation (easily
    thousands of tokens each).  Once the model has seen and responded to an
    image a few turns ago, keeping the raw image data provides diminishing
    returns while consuming enormous context budget.

    This walks backwards through the messages, counting assistant turns.
    Any image content found *before* the last ``IMAGE_RETAIN_TURNS`` assistant
    messages is replaced with a lightweight text placeholder.

    Returns ``True`` if any images were evicted.
    """
    # Count assistant turns from the end
    assistant_count = 0
    safe_boundary = len(messages)  # Index before which images are evictable
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get("role") == "assistant":
            assistant_count += 1
            if assistant_count >= IMAGE_RETAIN_TURNS:
                safe_boundary = idx
                break

    if safe_boundary == len(messages):
        # Not enough assistant turns yet; nothing to evict
        return False

    evicted = False
    for idx in range(safe_boundary):
        msg = messages[idx]
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        new_content = []
        had_image = False
        for item in content:
            if item.get("type") == "image_url":
                had_image = True
                # Skip (evict) this image block
                continue
            new_content.append(item)

        if had_image:
            evicted = True
            if new_content:
                # Inject a note so the model knows an image was here
                new_content.append({"type": "text", "text": "[image removed from context]"})
                msg["content"] = new_content
            else:
                # The entire message was just images; replace with text
                msg["content"] = "[image removed from context]"

    return evicted


def cap_tool_result_by_context(messages: list[dict], max_tokens: int) -> None:
    """Cap individual tool results to a fraction of the context window.

    Prevents a single massive tool result from crowding out everything else.
    Uses ``TOOL_RESULT_MAX_CONTEXT_SHARE`` of *max_tokens* (assuming ~4
    chars/token) as the per-result character limit.
    """
    # Approximate max chars allowed for a single tool result
    max_chars = int(max_tokens * 4 * TOOL_RESULT_MAX_CONTEXT_SHARE)
    if max_chars < 500:
        return

    for msg in messages:
        if msg.get("role") not in ("tool", "function"):
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
        if len(content) <= max_chars:
            continue
        half = max_chars // 2
        msg["content"] = (
            content[:half] + f"\n... [capped to {max_chars} chars of {len(content)} total] ...\n" + content[-half:]
        )


def get_callable_kwargs(func: Callable, payload: dict) -> dict:
    """Filter kwargs for callables that do not accept arbitrary keyword args."""
    try:
        parameters = signature(func).parameters.values()
    except (TypeError, ValueError):
        return payload

    if any(parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters):
        return payload

    allowed = {
        parameter.name
        for parameter in parameters
        if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
    }
    return {key: value for key, value in payload.items() if key in allowed}


@cog_i18n(_)
class ChatHandler(MixinMeta):
    async def get_mention_permissions(self, member: discord.Member) -> discord.AllowedMentions:
        """Return AllowedMentions allowing role/user pings for privileged members"""
        privileged = (
            member.id in self.bot.owner_ids
            or member.id == member.guild.owner_id
            or await self.bot.is_admin(member)
            or await self.bot.is_mod(member)
        )
        if privileged:
            return discord.AllowedMentions(everyone=False, roles=True, users=True)
        return discord.AllowedMentions(everyone=False, roles=False, users=False)

    async def request_tool_approval(
        self,
        function_name: str,
        function_entry: dict,
        arguments: dict,
        author: Optional[discord.Member],
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
        conversation: Conversation,
        message_obj: Optional[discord.Message],
    ) -> tuple[bool, str]:
        if not function_entry.get("requires_user_approval"):
            return True, ""
        if arguments.get("dry_run") is True:
            return True, ""
        if function_name in conversation.approved_tool_names:
            return True, ""

        if author is None or not hasattr(channel, "send") or message_obj is None:
            denial = _(
                "Execution of admin tool `{}` requires interactive approval, but no interactive message context was available."
            ).format(function_name)
            return False, denial

        source = function_entry.get("source", _("Unknown"))
        category = render_tool_category(function_entry.get("category"))
        preview = orjson.dumps(arguments, option=orjson.OPT_INDENT_2).decode()
        if len(preview) > 1200:
            preview = preview[:1200] + "\n... [truncated]"

        prompt = _(
            "`{}` wants to run admin tool `{}` from `{}` ({})\nChoose `Approve Once`, `Allow This Session`, or `Skip`."
        ).format(author.display_name, function_name, source, category)
        prompt += "\n" + box(preview, lang="json")

        reference = None
        with suppress(discord.HTTPException, AttributeError):
            reference = message_obj.to_reference(fail_if_not_exists=False)

        view = AdminToolApprovalView(author.id)
        approval_message = await channel.send(prompt, view=view, reference=reference)
        view.message = approval_message
        await view.wait()

        decision_map = {
            "once": _("Approved once."),
            "session": _("Approved for this session."),
            "skip": _("Skipped."),
            "timeout": _("Approval timed out."),
        }
        if view.decision == "session" and function_name not in conversation.approved_tool_names:
            conversation.approved_tool_names.append(function_name)

        with suppress(discord.HTTPException):
            await approval_message.edit(content=prompt + "\n" + decision_map[view.decision], view=view)

        if view.decision in {"once", "session"}:
            return True, ""

        if view.decision == "timeout":
            timed_out = _(
                "SKIPPED: Approval for admin tool `{}` timed out. Do not claim it ran. Continue without it, ask again later, or try a different tool."
            ).format(function_name)
            return False, timed_out

        denial = _(
            "SKIPPED: The user skipped admin tool `{}` for this call. Do not claim it ran. You may continue without it, ask for approval again later, or try a different tool."
        ).format(function_name)
        return False, denial

    async def resolve_prompt_context_variables(
        self,
        guild: discord.Guild,
        channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]],
        author: Optional[discord.Member],
        conf: GuildSettings,
        conversation: Conversation,
        extras: dict,
        now: datetime,
        prompt_templates: list[str],
    ) -> dict[str, str]:
        catalog = self.db.get_context_variable_catalog(self.bot, self.context_registry)
        if not catalog:
            return {}

        requested_names = {
            entry["name"]
            for entry in catalog
            if any(f"{{{entry['name']}}}" in template for template in prompt_templates if template)
        }
        if not requested_names:
            return {}

        prepared = await self.db.prep_context_variables(
            bot=self.bot,
            registry=self.context_registry,
            requested_names=requested_names,
            member=author,
        )

        payload = {
            **extras,
            "user": author,
            "channel": channel,
            "guild": guild,
            "bot": self.bot,
            "conf": conf,
            "conversation": conversation,
            "now": now,
        }
        resolved: dict[str, str] = {}
        for variable_name in sorted(requested_names):
            prepared_entry = prepared.get(variable_name)
            if prepared_entry is None:
                resolved[variable_name] = "Unavailable"
                continue

            fetcher = prepared_entry["callable"]
            fetch_kwargs = get_callable_kwargs(fetcher, payload)
            try:
                if iscoroutinefunction(fetcher):
                    value = await fetcher(**fetch_kwargs)
                else:
                    value = await asyncio.to_thread(fetcher, **fetch_kwargs)
            except Exception as e:
                log.error(f"Failed to resolve context variable {variable_name}", exc_info=e)
                resolved[variable_name] = f"[Error resolving {variable_name}]"
                continue

            if value is None:
                resolved[variable_name] = ""
            elif isinstance(value, (dict, list)):
                resolved[variable_name] = orjson.dumps(value, option=orjson.OPT_INDENT_2).decode()
            else:
                resolved[variable_name] = str(value)

        return resolved

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
        image_url_pattern = r"(https?:\/\/\S+\.(?:png|gif|webp|jpg|jpeg)(?:\?\S*)?)"

        # Extract the optional arguments and their values
        outputfile_match = re.search(outputfile_pattern, question)
        extract_match = re.search(extract_pattern, question)
        get_last_message_match = re.search(get_last_message_pattern, question)
        image_url_match = re.findall(image_url_pattern, question)

        # Remove the optional arguments from the input string to obtain the question variable
        question = re.sub(outputfile_pattern, "", question)
        question = re.sub(extract_pattern, "", question)
        question = re.sub(get_last_message_pattern, "", question)

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

            if has_extension and not i.filename.lower().endswith(tuple(READ_EXTENSIONS)):
                # Skip unsupported file types
                continue

            file_bytes = await i.read()

            # Check if this is a document type that needs special extraction
            if is_document(i.filename):
                text = await extract_document_text(i.filename, file_bytes)
                question += f"\n\n### Uploaded Document ({i.filename}):\n{text}\n"
                continue

            # Handle as text file
            if isinstance(file_bytes, bytes):
                try:
                    text = file_bytes.decode()
                except UnicodeDecodeError:
                    text = f"[Unable to decode file: {i.filename}]"
                except Exception as e:
                    log.error(f"Failed to decode content of {i.filename}", exc_info=e)
                    text = f"[Failed to read file: {i.filename}]"
            else:
                text = file_bytes

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
            deferred_files = []
        else:
            deferred_files = []
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
                    deferred_files=deferred_files,
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
                self.bot._last_exception = f"{traceback.format_exc()}\nAPI Status: {status}"  # type: ignore
                reply = _("Uh oh, something went wrong! Bot owner can use `{}` to view the error.").format(
                    f"{prefix}traceback"
                )
                reply += "\n\n" + _("API Status: {}").format(status)

        if reply is None:
            return

        allowed_mentions = await self.get_mention_permissions(message.author)

        files = None
        to_send = []
        if outputfile and not extract:
            # Everything to file
            all_files = [discord.File(BytesIO(reply.encode()), filename=outputfile)] + deferred_files
            return await message.reply(files=all_files, mention_author=conf.mention, allowed_mentions=allowed_mentions)
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

        if deferred_files:
            files = (files or []) + deferred_files

        for index, text in enumerate(to_send):
            if index == 0:
                await send_reply(
                    message=message,
                    content=text,
                    conf=conf,
                    files=files,
                    reply=True,
                    allowed_mentions=allowed_mentions,
                    include_think_files=self.db.reasoning_as_files,
                )
            else:
                await send_reply(
                    message=message,
                    content=text,
                    conf=conf,
                    allowed_mentions=allowed_mentions,
                    include_think_files=self.db.reasoning_as_files,
                )

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
        deferred_files: Optional[List[discord.File]] = None,
    ) -> Union[str, None]:
        """Call the API asynchronously"""
        functions = function_calls.copy() if function_calls else []
        mapping = function_map.copy() if function_map else {}
        function_entries: Dict[str, dict] = {}

        async def do_not_respond(*args, **kwargs):
            return {"return_null": True, "content": "do_not_respond"}

        if conf.use_function_calls and extend_function_calls:
            # Prepare registry and custom functions
            prepped_function_calls, prepped_function_map = await self.db.prep_functions(
                bot=self.bot, conf=conf, registry=self.registry, member=author
            )
            catalog_map = {entry["name"]: entry for entry in self.db.get_function_catalog(self.bot, self.registry)}
            functions.extend(prepped_function_calls)
            mapping.update(prepped_function_map)
            for function_name in prepped_function_map:
                if function_name in catalog_map:
                    function_entries[function_name] = catalog_map[function_name]
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
                function_entries=function_entries,
                message_obj=message_obj,
                images=images,
                model_override=model_override,
                auto_answer=auto_answer,
                trigger_prompt=trigger_prompt,
                deferred_files=deferred_files,
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
        function_entries: Dict[str, dict],
        message_obj: Optional[discord.Message] = None,
        images: list[str] = None,
        model_override: Optional[str] = None,
        auto_answer: Optional[bool] = False,
        trigger_prompt: Optional[str] = None,
        deferred_files: Optional[List[discord.File]] = None,
    ) -> Union[str, None]:
        if isinstance(author, int):
            author = guild.get_member(author)
        if isinstance(channel, int):
            channel = guild.get_channel(channel)

        member = author if isinstance(author, discord.Member) else guild.get_member(author)
        allowed_mentions = await self.get_mention_permissions(member) if member else discord.AllowedMentions.none()

        query_embedding = []
        user = author if isinstance(author, discord.Member) else guild.get_member(author)
        user_id = author.id if isinstance(author, discord.Member) else author
        model = conf.get_user_model(user)

        # Ensure the message is not longer than 1048576 characters
        message = message[:1048576]

        # Determine if we should embed the user's message
        message_tokens = await self.count_tokens(message, model)
        words = message.split(" ")
        has_embeds = await self.embedding_store.has_embeddings(guild.id)
        get_embed_conditions = [
            has_embeds,  # We actually have embeddings to compare with
            len(words) > 1,  # Message is long enough
            conf.top_n,  # Top n is greater than 0
            message_tokens < 8191,
        ]
        if all(get_embed_conditions):
            try:
                if conf.question_mode:
                    # If question mode is enabled, only the first message and messages that end with a ? will be embedded
                    if message.endswith("?") or not conversation.messages:
                        query_embedding = await self.request_embedding(message, conf)
                else:
                    query_embedding = await self.request_embedding(message, conf)
            except Exception as e:
                log.error("Failed to get query embedding, continuing without embeddings", exc_info=e)

        log.debug(f"Query embedding: {len(query_embedding)}")

        mem = guild.get_member(author) if isinstance(author, int) else author
        bal = humanize_number(await bank.get_balance(mem)) if mem else _("None")
        extras = {
            "banktype": "global bank" if await bank.is_global() else "local bank",
            "currency": await bank.get_currency_name(guild),
            "bank": await bank.get_bank_name(guild),
            "balance": bal,
        }

        # Don't include if user is not a planner
        not_planner = [
            user_id not in conf.planners,
            not any([role.id in conf.planners for role in user.roles]),
        ]

        # Don't include think_and_plan if user is not a planner (and planners list is not empty)
        if "think_and_plan" in function_map and conf.planners and all(not_planner):
            function_calls = [i for i in function_calls if i["name"] != "think_and_plan"]
            del function_map["think_and_plan"]

        if "edit_image" in function_map and (not conversation.get_images() and not images):
            function_calls = [i for i in function_calls if i["name"] != "edit_image"]
            del function_map["edit_image"]

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
        reply_reasoning = ""

        calls = 0
        tries = 0
        tool_call_history: dict[str, int] = {}  # Track (name, args) -> count for loop detection
        last_sent_content: str = ""  # Track content already sent via respond_and_continue
        while True:
            if tries > 2:
                log.error("Breaking after 3 retries (image purge or empty model response)")
                break
            if calls >= conf.max_function_calls:
                function_calls = []

            supports_vision = await self.endpoint_supports_vision(conf, author, requested_model=model)
            if not supports_vision:
                await ensure_supports_vision(messages, conf, author)
            await ensure_message_compatibility(messages, conf, author)
            if self.db.endpoint_override:
                # Replace "developer" role with "system" role
                for i in messages:
                    if i["role"] == "developer":
                        i["role"] = "system"

            # Evict images from older turns to free up massive token cost
            evicted = evict_old_images(messages)

            # Compute context fill ratio for context-aware pruning
            max_tokens = self.get_max_tokens(conf, author)
            convo_tokens = await self.count_payload_tokens(messages, model)
            func_tokens = await self.count_function_tokens(function_calls, model)
            context_fill_ratio = (convo_tokens + func_tokens) / max_tokens if max_tokens else 0.0

            # Cap individual tool results to a fraction of the context window
            cap_tool_result_by_context(messages, max_tokens)

            # Two-tier prune old tool results based on context pressure
            prune_old_tool_results(messages, context_fill_ratio)

            # Multi-layer context management:
            # 1. Flush important user facts to memory before compaction
            # 2. Compact via LLM summarization (falls back to blind degradation)
            await self.flush_memory_before_compaction(messages, conf, author, guild)
            compacted = await self.compact_conversation(
                messages, function_calls, conf, author, conversation=conversation
            )
            degraded = compacted

            if compacted and message_obj:
                with suppress(discord.HTTPException):
                    await message_obj.add_reaction("🗜️")

            before = len(messages)
            cleaned = await ensure_tool_consistency(messages)
            if cleaned and before == len(messages):
                log.error("Something went wrong while ensuring tool call consistency")

            await clean_responses(messages)

            if cleaned or degraded or evicted:
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
                    dump_file = text_to_file(
                        orjson.dumps(messages, option=orjson.OPT_INDENT_2).decode(),
                        filename=f"{author}_convo_BadRequest.json",
                    )
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
                    dump_file = text_to_file(
                        orjson.dumps(messages, option=orjson.OPT_INDENT_2).decode(),
                        filename=f"{author}_convo_Exception.json",
                    )
                    await channel.send(file=dump_file)

                raise e

            reasoning_content = getattr(response, "reasoning_content", None)
            reply_reasoning = reasoning_content.strip() if isinstance(reasoning_content, str) else ""

            if reply := response.content:
                break

            # Check for model refusal (newer API field)
            if hasattr(response, "refusal") and response.refusal:
                log.error(f"Model refused to respond: {response.refusal}")
                reply = response.refusal
                break

            await clean_response(response)

            if response.tool_calls:
                log.debug("Tool calls detected")
                response_functions: list[ChatCompletionMessageToolCall] = response.tool_calls
            elif response.function_call:
                log.debug("Function call detected")
                response_functions: list[FunctionCall] = [response.function_call]
            else:
                tries += 1
                log.warning(
                    f"No reply and no function calls from model (attempt {tries}). "
                    f"Response dump: {response.model_dump()}"
                )
                continue

            if len(response_functions) > 1:
                log.debug(f"Calling {len(response_functions)} functions at once")

            dump = response.model_dump()
            if not dump["function_call"]:
                del dump["function_call"]
            if not dump["tool_calls"]:
                del dump["tool_calls"]
            dump.pop("reasoning_content", None)

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

                # Loop detection: track repeated identical tool calls
                call_key = f"{function_name}:{arguments}"
                tool_call_history[call_key] = tool_call_history.get(call_key, 0) + 1
                if tool_call_history[call_key] > 2:
                    log.warning(
                        f"Tool loop detected: {function_name} called {tool_call_history[call_key]} times with same args"
                    )
                    e = {
                        "role": role,
                        "name": function_name,
                        "content": (
                            f"ERROR: You have already called {function_name} with these exact arguments "
                            f"{tool_call_history[call_key]} times. Stop calling this function repeatedly and "
                            "respond to the user with the information you already have."
                        ),
                    }
                    if tool_id:
                        e["tool_call_id"] = tool_id
                    messages.append(e)
                    conversation.messages.append(e)
                    # Remove the tool to prevent further calls
                    function_calls = [i for i in function_calls if i["name"] != function_name]
                    if function_name in function_map:
                        del function_map[function_name]
                    continue

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

                try:
                    args = orjson.loads(arguments)
                    func_result = None
                except orjson.JSONDecodeError as e:
                    func_result = f"JSONDecodeError: Failed to parse arguments for function {function_name}: {str(e)}"
                except Exception as e:
                    log.error(f"Unexpected error parsing arguments for function {function_name}", exc_info=e)
                    func_result = f"Error: Failed to parse arguments for function {function_name}: {str(e)}"

                if func_result is None:
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
                        approved, denial_reason = await self.request_tool_approval(
                            function_name=function_name,
                            function_entry=function_entries.get(function_name, {}),
                            arguments=args,
                            author=member,
                            channel=channel,
                            conversation=conversation,
                            message_obj=message_obj,
                        )
                        if not approved:
                            func_result = denial_reason
                        elif iscoroutinefunction(func):
                            func_result = await func(**kwargs)
                        else:
                            func_result = await asyncio.to_thread(func, **kwargs)
                        if function_name == "respond_and_continue":
                            last_sent_content = args.get("content", "")
                    except Exception as e:
                        log.error(
                            f"Custom function {function_name} failed to execute!\nArgs: {arguments}",
                            exc_info=e,
                        )
                        func_result = f"Unexpected error executing function {function_name}:\n{traceback.format_exc()}"
                        function_calls = [i for i in function_calls if i["name"] != function_name]

                return_null = False

                if isinstance(func_result, discord.Embed):
                    content = func_result.description or _("Result sent!")
                    try:
                        await channel.send(embed=func_result, allowed_mentions=allowed_mentions)
                    except discord.Forbidden:
                        content = "You do not have permissions to embed links in this channel"
                        function_calls = [i for i in function_calls if i["name"] != function_name]
                elif isinstance(func_result, discord.File):
                    content = "File generated, it will be attached to the response."
                    if deferred_files is not None:
                        deferred_files.append(func_result)
                    else:
                        try:
                            await channel.send(file=func_result, allowed_mentions=allowed_mentions)
                        except discord.Forbidden:
                            content = "You do not have permissions to upload files in this channel"
                            function_calls = [i for i in function_calls if i["name"] != function_name]
                elif isinstance(func_result, dict):
                    # For complex responses
                    content = func_result.get("result_text")
                    if not content:
                        content = func_result.get("content")
                    return_null = func_result.get("return_null", False)

                    # Collect deferred files for attachment to the final reply
                    if "defer_files" in func_result and deferred_files is not None:
                        for f in func_result["defer_files"]:
                            if isinstance(f, discord.File):
                                deferred_files.append(f)

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
                            await channel.send(**kwargs, allowed_mentions=allowed_mentions)
                        except discord.HTTPException as e:
                            content = f"discord.HTTPException: {e.text}"
                            function_calls = [i for i in function_calls if i["name"] != function_name]
                    if content is None and kwargs:
                        content = _("Result sent!")

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

                if content is None:
                    content = _("Result sent!")

                e = {"role": role, "name": function_name, "content": content}
                if tool_id:
                    e["tool_call_id"] = tool_id
                messages.append(e)
                conversation.messages.append(e)

                if return_null:
                    if deferred_files:
                        try:
                            await channel.send(files=deferred_files, allowed_mentions=allowed_mentions)
                        except discord.HTTPException:
                            pass
                        deferred_files.clear()
                    return None

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

        # Suppress duplicate if respond_and_continue already sent the same content
        if last_sent_content and reply and reply.strip() == last_sent_content.strip():
            log.debug("Suppressing duplicate reply already sent via respond_and_continue")
            return None

        return append_reasoning_block(reply, reply_reasoning, conf)

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
        configured_model = conf.get_user_model(author)
        current_model = self.resolve_chat_model(configured_model)
        current_embed_model = self.resolve_embedding_model(conf.embed_model)
        reasoning_effort = conf.get_user_reasoning_effort(author)
        configured_max_tokens = conf.get_user_max_tokens(author)
        max_tokens = self.get_max_tokens(conf, author)
        max_response_tokens = conf.get_user_max_response_tokens(author)

        profile = self.get_cached_endpoint_profile()
        model_max_context = (
            self.get_endpoint_chat_model_limit(current_model)
            if self.db.endpoint_override
            else MODELS.get(current_model, 0)
        )
        configured_max_text = humanize_number(configured_max_tokens) if configured_max_tokens else "Model Max"

        if profile:
            modelinfo_lines = [
                line.replace("`", "").rstrip() for line in self.describe_endpoint_profile(profile).splitlines()
            ]
        else:
            modelinfo_lines = [
                f"Chat Model: {current_model}",
                f"Embedding Model: {current_embed_model}",
                f"Max Context: {humanize_number(model_max_context) if model_max_context else 'Unknown'}",
            ]

        if profile:
            if configured_model != current_model:
                modelinfo_lines.append(f"Configured Chat Model: {configured_model}")
            if conf.embed_model != current_embed_model:
                modelinfo_lines.append(f"Configured Embed Model: {conf.embed_model}")

        modelinfo_lines.extend(
            [
                f"Configured Max Tokens (Cog): {configured_max_text}",
                f"Effective Max Tokens: {humanize_number(max_tokens)}",
                f"Reasoning Effort: {reasoning_effort}",
                f"Verbosity: {conf.verbosity}",
            ]
        )

        if max_response_tokens:
            modelinfo_lines.append(f"Configured Max Response Tokens (Cog): {humanize_number(max_response_tokens)}")

        modelinfo = "\n".join(modelinfo_lines)
        valid_prefixes = await self.bot.get_valid_prefixes(guild)
        prefix = valid_prefixes[0] if valid_prefixes else ""
        prefixes = humanize_list(valid_prefixes)
        params = await asyncio.to_thread(
            get_params,
            self.bot,
            guild,
            now,
            author,
            channel,
            extras,
            current_model,
            modelinfo,
            prefix,
            prefixes,
        )

        selected_system_prompt = (
            conf.channel_prompts[channel.id]
            if channel.id in conf.channel_prompts
            else conversation.system_prompt_override or self.db.get_effective_system_prompt(conf)
        )
        prompt_templates = [selected_system_prompt, conf.prompt, trigger_prompt or ""]
        context_variables = await self.resolve_prompt_context_variables(
            guild=guild,
            channel=channel,
            author=author,
            conf=conf,
            conversation=conversation,
            extras=extras,
            now=now,
            prompt_templates=prompt_templates,
        )
        for variable_name, value in context_variables.items():
            if variable_name in params:
                log.warning(
                    f"Context variable {variable_name} conflicts with a built-in prompt parameter and was skipped"
                )
                continue
            params[variable_name] = value

        def format_string(text: str):
            """Instead of format(**params) possibly giving a KeyError if prompt has code in it"""
            for k, v in params.items():
                key = "{" + k + "}"
                text = text.replace(key, str(v))
            return text

        if channel.id in conf.channel_prompts:
            system_prompt = format_string(conf.channel_prompts[channel.id])
        else:
            system_prompt = format_string(
                conversation.system_prompt_override or self.db.get_effective_system_prompt(conf)
            )

        initial_prompt = format_string(conf.prompt)
        model = configured_model
        current_tokens = await self.count_tokens(message + system_prompt + initial_prompt, model)
        current_tokens += await self.count_payload_tokens(conversation.messages, model)
        current_tokens += await self.count_function_tokens(function_calls, model)

        related = await self.embedding_store.get_related(
            guild_id=guild.id,
            query_embedding=query_embedding,
            top_n=conf.top_n,
            min_relatedness=conf.min_relatedness,
        )

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

        # Inject user memories if available
        if author:
            memory_key = f"{guild.id}-{author.id}"
            user_memory = self.db.user_memories.get(memory_key)
            if user_memory and user_memory.facts:
                facts_text = "\n".join(f"- {fact}" for fact in user_memory.facts)
                system_prompt += f"\n\n[Known facts about {author.display_name}]\n{facts_text}"

        if auto_answer:
            initial_prompt += (
                "\n# AUTO ANSWER:\nYou are responding to a triggered event not specifically requested by the user. "
                "You may opt to not respond if necessary by calling the `do_not_respond` function.\n"
                "If you do not have access to functions, you may respond with the exact phrase `do_not_respond`"
            )

        if trigger_prompt:
            formatted_trigger = format_string(trigger_prompt)
            initial_prompt += f"\n# TRIGGER RESPONSE:\n{formatted_trigger}"

        supports_vision = await self.endpoint_supports_vision(conf, author, requested_model=model)
        images = images if supports_vision else []
        messages = conversation.prepare_chat(
            message,
            initial_prompt.strip(),
            system_prompt.strip(),
            name=clean_name(author.name) if author else None,
            images=images,
            resolution=conf.vision_detail,
        )
        return messages
