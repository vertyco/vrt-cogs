import logging
from datetime import datetime

import discord
import openai
import pytz
from discord import app_commands
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..common import constants as C, utils
from ..common.ai_responses import CommandCreationResponse
from ..common.models import ScheduledCommand
from ..components.task_menu import TaskMenu

log = logging.getLogger("red.vrt.taskr.commands.admin")
_ = Translator("Taskr", __file__)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.hybrid_command(name="taskr", description=_("Open the task menu"), aliases=["tasker"])
    @commands.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def taskr(self, ctx: commands.Context, *, query: str = ""):
        """Open the task menu"""
        await TaskMenu(ctx, query).start()

    @taskr.autocomplete("query")
    async def _taskr_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        return [
            app_commands.Choice(name=x.name, value=x.name)
            for x in self.db.tasks.values()
            if current.casefold() in x.casefold() and x.guild_id == interaction.guild.id
        ][:25]

    @commands.hybrid_command(name="tasktimezone")
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        """Set the timezone used for scheduled tasks in this server"""
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            likely_match = sorted(
                pytz.common_timezones,
                key=lambda x: fuzz.ratio(timezone.lower(), x.lower()),
                reverse=True,
            )[0]
            return await ctx.send(_("Invalid Timezone, did you mean `{}`?").format(likely_match))
        self.db.timezones[ctx.guild.id] = timezone
        self.save()
        await ctx.send(_("Timezone set to {}").format(timezone))

    @set_timezone.autocomplete("timezone")
    async def _timezone_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        return [
            app_commands.Choice(name=x, value=x) for x in pytz.common_timezones if current.casefold() in x.casefold()
        ][:25]

    @commands.hybrid_command(name="aitask", description=_("Create a scheduled task using AI"))
    @commands.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def ai_task(self, ctx: commands.Context, *, request: str):
        """Create a scheduled task using AI

        Example requests:
        - Please run the ping command every second friday at 3pm starting in January
        - Please run the ping command every odd hour at the 30 minute mark from 5am to 8pm
        - Please run the ping command on the 15th of each month at 3pm
        """
        openai_token = None
        keys = await self.bot.get_shared_api_tokens("openai")
        if keys and keys.get("api_key"):
            openai_token = keys["api_key"]
            if not openai_token and "key" in keys:
                openai_token = keys["key"]

        if not openai_token:
            all_tokens = await self.bot.get_shared_api_tokens()
            for service_name, tokens in all_tokens.items():
                if "openai" in service_name:
                    openai_token = tokens.get("api_key") or tokens.get("key")  # type: ignore

        if not openai_token:
            return await ctx.send(
                _("No OpenAI token set. run `[p]set api openai key <key>` to set one."), ephemeral=True
            )

        timezone = self.db.timezone(ctx.guild.id)
        now = datetime.now(pytz.timezone(timezone))
        formatted_time = now.strftime("%A, %B %d, %Y %I:%M%p %Z")

        details = f"Current user ID: {ctx.author.id}\nCurrent channel ID: {ctx.channel.id}\n"
        messages = [
            {"role": "developer", "content": f"The current time is {formatted_time}"},
            {"role": "developer", "content": C.SYSTEM_PROMPT},
            {"role": "developer", "content": f"Context:\n{details}"},
            {"role": "developer", "content": "Your task is to create a scheduled command using the details provided."},
            {"role": "user", "content": request},
        ]
        try:
            client = openai.AsyncClient(api_key=openai_token)
            response = await client.beta.chat.completions.parse(
                model="gpt-5",
                messages=messages,
                response_format=CommandCreationResponse,
                reasoning_effort="minimal",
            )
            model: CommandCreationResponse = response.choices[0].message.parsed
        except Exception as e:
            log.error("Failed to get cron expression from AI model", exc_info=e)
            return await ctx.send(
                _("Failed to get response from AI model, please try again later or check the logs for more info."),
                ephemeral=True,
            )

        dump = model.model_dump(mode="json")
        dump["guild_id"] = ctx.guild.id

        chan_or_thread = ctx.guild.get_channel_or_thread(dump.get("channel_id", 0))
        if chan_or_thread and not chan_or_thread.permissions_for(ctx.author).send_messages:
            dump["channel_id"] = ctx.channel.id
        elif not chan_or_thread:
            dump["channel_id"] = ctx.channel.id

        cmd_author = ctx.guild.get_member(dump.get("author_id", 0))
        if cmd_author and cmd_author.top_role > ctx.author.top_role:
            dump["author_id"] = ctx.author.id
        elif not cmd_author:
            dump["author_id"] = ctx.author.id

        try:
            command = ScheduledCommand.model_validate(dump)
        except Exception as e:
            log.error("Failed to create ScheduledCommand from AI model response", exc_info=e)
            return await ctx.send(
                _("Failed to create scheduled command from AI model response, please check the logs for more info."),
                ephemeral=True,
            )

        if not command.is_safe(self.db.timezone(ctx.guild.id), self.db.minimum_interval):
            return await ctx.send(_("The command generated by the AI model is not safe to run."), ephemeral=True)

        log.debug("AI Generated Command: %s", command.model_dump_json(indent=2))

        command_channel = ctx.guild.get_channel_or_thread(command.channel_id)
        command_author = ctx.guild.get_member(command.author_id)

        user_perms = command_channel.permissions_for(ctx.author)
        bot_perms = command_channel.permissions_for(ctx.guild.me)
        context = await utils.invoke_command(
            bot=self.bot,
            author=command_author,
            channel=command_channel,
            command=command.command,
            message=ctx.message,
            invoke=False,
        )
        try:
            if not context.valid:
                return await ctx.send(_("This command does not exist."), ephemeral=True)
            elif (
                not await discord.utils.async_all([check(context) for check in context.command.checks])
                or not user_perms.send_messages
                or not bot_perms.send_messages
            ):
                return await ctx.send(_("You do not have permission to run this command."), ephemeral=True)
            elif context.command.qualified_name in ("shutdown", "restart", "reload", "unload", "load"):
                return await ctx.send(_("This command cannot be scheduled."), ephemeral=True)
        except Exception as e:
            log.error("Failed to validate command permissions", exc_info=e)
            return await ctx.send(
                _("Failed to validate command permissions, please check the logs for more info."), ephemeral=True
            )
        self.db.add_task(command)
        self.save()
        await ctx.send(_("Scheduled command created successfully."), ephemeral=True)
        await TaskMenu(ctx, command.id).start()
