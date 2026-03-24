import io
import secrets
import textwrap

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common.models import Survey

APPS_SCRIPT_TEMPLATE = textwrap.dedent("""\
    function onSubmit(e) {{
      var responses = e.response.getItemResponses();
      var discordId = "";
      for (var i = 0; i < responses.length; i++) {{
        if (responses[i].getItem().getTitle() === "{discord_field}") {{
          discordId = responses[i].getResponse().trim();
          break;
        }}
      }}
      if (!discordId) return;

      var payload = {{
        "content": "Discord User ID: " + discordId
      }};

      var options = {{
        "method": "post",
        "contentType": "application/json",
        "payload": JSON.stringify(payload),
        "muteHttpExceptions": true
      }};

      UrlFetchApp.fetch("{webhook_url}", options);
    }}
""")


class Admin(MixinMeta):
    @commands.group(name="gsurveys", aliases=["gsurvey"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def gsurveys(self, ctx: commands.Context):
        """Manage Google Form survey rewards.

        This cog lets you link Google Forms to your server's economy.
        When a user fills out a form and enters their Discord User ID,
        they automatically receive virtual currency as a reward.

        **Quick Start:**
        1. `[p]gsurveys add #channel <reward> <name>` — create a survey
        2. `[p]gsurveys script <survey_id>` — get the Google Apps Script
        3. Add the script to your form and you're done!

        **Finding a survey ID:**
        Survey IDs are shown when you create a survey and in `[p]gsurveys list`.
        They look like short hex codes, e.g. `a1b2c3d4e5f6`.
        """

    @gsurveys.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def gsurveys_add(self, ctx: commands.Context, channel: discord.TextChannel, reward: int, *, name: str):
        """Add a new survey.

        The bot will create a Discord webhook in the specified channel to receive
        Google Form responses. Choose a private channel that only the bot and
        admins can see — webhook messages are deleted automatically but the
        channel should not be publicly visible.

        **Arguments**
        - `channel`: The channel to receive form submissions in (use a private channel).
        - `reward`: The amount of credits to award on completion.
        - `name`: A display name for this survey.
        """
        if reward <= 0:
            return await ctx.send("Reward must be a positive number.")

        # Create a Discord webhook in the target channel
        try:
            webhook = await channel.create_webhook(name=f"GSurvey: {name}")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to create webhooks in that channel.")
        except discord.HTTPException as e:
            return await ctx.send(f"Failed to create webhook: {e}")

        conf = self.db.get_conf(ctx.guild)
        survey_id = secrets.token_hex(6)
        conf.surveys[survey_id] = Survey(
            name=name,
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            webhook_id=webhook.id,
            webhook_url=webhook.url,
            reward=reward,
        )
        self.save()

        msg = (
            f"**Survey created!**\n"
            f"**Name:** {name}\n"
            f"**ID:** `{survey_id}`\n"
            f"**Reward:** {reward} credits\n"
            f"**Channel:** {channel.mention}\n\n"
            f"Use `{ctx.clean_prefix}gsurveys script {survey_id}` to get the Google Apps Script."
        )
        await ctx.send(msg)

    @gsurveys.command(name="remove")
    @commands.bot_has_permissions(manage_webhooks=True)
    async def gsurveys_remove(self, ctx: commands.Context, survey_id: str):
        """Remove a survey by its ID.

        This also deletes the associated Discord webhook.
        """
        conf = self.db.get_conf(ctx.guild)
        if survey_id not in conf.surveys:
            return await ctx.send("Survey not found.")

        survey = conf.surveys.pop(survey_id)

        # Try to delete the webhook
        try:
            webhook = await self.bot.fetch_webhook(survey.webhook_id)
            await webhook.delete(reason=f"GSurvey '{survey.name}' removed")
        except (discord.NotFound, discord.Forbidden):
            pass

        self.save()
        await ctx.send(f"Survey **{survey.name}** (`{survey_id}`) removed.")

    @gsurveys.command(name="list")
    async def gsurveys_list(self, ctx: commands.Context):
        """List all surveys for this server."""
        conf = self.db.get_conf(ctx.guild)
        if not conf.surveys:
            return await ctx.send("No surveys configured.")

        lines = []
        for sid, survey in conf.surveys.items():
            status = "Enabled" if survey.enabled else "Disabled"
            total = len(survey.completions)
            lines.append(
                f"**{survey.name}** (`{sid}`)\n"
                f"  Reward: {survey.reward} | "
                f"Status: {status} | Channel: <#{survey.channel_id}> | Completions: {total}"
            )

        text = "\n\n".join(lines)
        for page in pagify(text, page_length=1900):
            await ctx.send(page)

    @gsurveys.command(name="view")
    async def gsurveys_settings(self, ctx: commands.Context):
        """View the current settings for this server."""
        conf = self.db.get_conf(ctx.guild)
        log_ch = f"<#{conf.log_channel}>" if conf.log_channel else "Not set"
        notify_ch = f"<#{conf.notify_channel}>" if conf.notify_channel else "Not set"
        survey_count = len(conf.surveys)
        enabled_count = sum(1 for s in conf.surveys.values() if s.enabled)

        text = (
            f"**GSurveys Settings**\n"
            f"**Log Channel:** {log_ch}\n"
            f"**Notify Channel:** {notify_ch}\n"
            f"**Surveys:** {survey_count} total, {enabled_count} enabled"
        )
        await ctx.send(text)

    @gsurveys.command(name="toggle")
    async def gsurveys_toggle(self, ctx: commands.Context, survey_id: str):
        """Enable or disable a survey."""
        conf = self.db.get_conf(ctx.guild)
        survey = conf.surveys.get(survey_id)
        if not survey:
            return await ctx.send("Survey not found.")
        survey.enabled = not survey.enabled
        self.save()
        state = "enabled" if survey.enabled else "disabled"
        await ctx.send(f"Survey **{survey.name}** is now **{state}**.")

    @gsurveys.command(name="reward")
    async def gsurveys_reward(self, ctx: commands.Context, survey_id: str, reward: int):
        """Change the reward amount for a survey."""
        if reward <= 0:
            return await ctx.send("Reward must be a positive number.")
        conf = self.db.get_conf(ctx.guild)
        survey = conf.surveys.get(survey_id)
        if not survey:
            return await ctx.send("Survey not found.")
        survey.reward = reward
        self.save()
        await ctx.send(f"Reward for **{survey.name}** set to **{reward}** credits.")

    @gsurveys.command(name="field")
    async def gsurveys_field(self, ctx: commands.Context, survey_id: str, *, field_name: str):
        """Set the Google Form question title that collects the Discord User ID.

        This must match the exact title of the question in your Google Form.
        Default is \"Discord User ID\".
        """
        conf = self.db.get_conf(ctx.guild)
        survey = conf.surveys.get(survey_id)
        if not survey:
            return await ctx.send("Survey not found.")
        survey.discord_field = field_name
        self.save()
        await ctx.send(
            f"Discord field for **{survey.name}** set to **{field_name}**.\n"
            f"Make sure to regenerate the Apps Script with `{ctx.clean_prefix}gsurveys script {survey_id}`."
        )

    @gsurveys.command(name="completions")
    async def gsurveys_completions(self, ctx: commands.Context, survey_id: str):
        """View who has completed a survey."""
        conf = self.db.get_conf(ctx.guild)
        survey = conf.surveys.get(survey_id)
        if not survey:
            return await ctx.send("Survey not found.")

        if not survey.completions:
            return await ctx.send(f"No completions for **{survey.name}** yet.")

        lines = []
        for uid in survey.completions:
            member = ctx.guild.get_member(uid)
            display = str(member) if member else f"Unknown ({uid})"
            lines.append(display)

        text = f"**Completions for {survey.name} ({len(lines)} total):**\n" + "\n".join(lines)
        for page in pagify(text, page_length=1900):
            await ctx.send(page)

    @gsurveys.command(name="reset")
    async def gsurveys_reset(self, ctx: commands.Context, survey_id: str):
        """Reset all completions for a survey.

        This clears the completion history so all users can fill it out again.
        Credits already awarded are **not** taken back.
        """
        conf = self.db.get_conf(ctx.guild)
        survey = conf.surveys.get(survey_id)
        if not survey:
            return await ctx.send("Survey not found.")

        count = len(survey.completions)
        survey.completions.clear()
        self.save()
        await ctx.send(f"Cleared **{count}** completion(s) for **{survey.name}**.")

    @gsurveys.command(name="resetuser")
    async def gsurveys_resetuser(self, ctx: commands.Context, survey_id: str, user: discord.Member):
        """Reset a specific user's completion for a survey.

        This allows the user to fill out the survey and be rewarded again.
        Credits already awarded are **not** taken back.
        """
        conf = self.db.get_conf(ctx.guild)
        survey = conf.surveys.get(survey_id)
        if not survey:
            return await ctx.send("Survey not found.")

        if user.id not in survey.completions:
            return await ctx.send(f"{user.mention} has not completed this survey.")

        survey.completions.discard(user.id)
        self.save()
        await ctx.send(f"Reset completion for {user.mention} on **{survey.name}**.")

    @gsurveys.command(name="logchannel")
    async def gsurveys_logchannel(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        """Set or clear the log channel for survey completions.

        When set, the bot posts a message here each time someone completes a survey.
        Run without a channel to clear it.
        """
        conf = self.db.get_conf(ctx.guild)
        if channel is None:
            conf.log_channel = 0
            self.save()
            return await ctx.send("Log channel cleared.")
        conf.log_channel = channel.id
        self.save()
        await ctx.send(f"Survey completion logs will be sent to {channel.mention}.")

    @gsurveys.command(name="notifychannel")
    async def gsurveys_notifychannel(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        """Set or clear the public notification channel.

        If the bot can't DM a user after they complete a survey, it will
        mention them in this channel instead so they know they were rewarded.
        Run without a channel to clear it.
        """
        conf = self.db.get_conf(ctx.guild)
        if channel is None:
            conf.notify_channel = 0
            self.save()
            return await ctx.send("Notification channel cleared.")
        conf.notify_channel = channel.id
        self.save()
        await ctx.send(f"DM fallback notifications will be sent to {channel.mention}.")

    @gsurveys.command(name="script")
    @commands.bot_has_permissions(attach_files=True)
    async def gsurveys_script(self, ctx: commands.Context, survey_id: str):
        """Get the Google Apps Script to attach to your Google Form.

        The script is sent via DM to avoid leaking the webhook URL.
        Find the survey ID from `[p]gsurveys list` or when you first created the survey.
        """
        conf = self.db.get_conf(ctx.guild)
        survey = conf.surveys.get(survey_id)
        if not survey:
            return await ctx.send("Survey not found.")

        script = APPS_SCRIPT_TEMPLATE.format(
            discord_field=survey.discord_field,
            webhook_url=survey.webhook_url,
        )

        instructions = (
            f"**Google Apps Script for survey: {survey.name}**\n\n"
            "**Setup instructions:**\n"
            "1. Open your Google Form in edit mode\n"
            "2. Click the three-dot menu (top right) > **Apps Script**\n"
            "3. Delete any existing code and paste the contents of the attached file\n"
            "4. Click **Save** (Ctrl+S)\n"
            "5. In the script editor, go to **Triggers** (clock icon on the left)\n"
            "6. Click **+ Add Trigger** and set:\n"
            "   - Function: `onSubmit`\n"
            "   - Event source: **From form**\n"
            "   - Event type: **On form submit**\n"
            "7. Click **Save** and authorize the script\n\n"
            f"**Important:** Your form MUST have a question titled exactly "
            f'**"{survey.discord_field}"** where users enter their Discord User ID.\n\n'
            "**Tip for your form:** Add a description to the Discord User ID question "
            "explaining how to find it:\n"
            "> *Open Discord > Settings > Advanced > Enable Developer Mode. "
            "Then right-click your name and select Copy User ID. "
            f"Or run the `{ctx.clean_prefix}myid` command in the server.*\n\n"
            "**Response Validation (recommended):**\n"
            "Set the Discord User ID question to validate input so users can't "
            "accidentally submit a username instead of their numeric ID:\n"
            "1. Click the Discord User ID question in the form editor\n"
            "2. Click the **three-dot menu** (bottom right of the question) > **Response validation**\n"
            "3. Set it to **Regular expression** > **Matches** > `^\\d{17,20}$`\n"
            "4. Set a custom error message, e.g.:\n"
            "> *Please enter your numeric Discord User ID. "
            "Right-click your name in Discord and select Copy User ID.*"
        )

        script_file = discord.File(io.BytesIO(script.encode()), filename=f"{survey.name}.js")

        try:
            await ctx.author.send(instructions, file=script_file)
            await ctx.send("Apps Script instructions sent to your DMs!")
        except discord.Forbidden:
            await ctx.send("I couldn't DM you. Please enable DMs from server members.")
