import discord
from chat_exporter import chat_exporter
from redbot.core import commands
from redbot.core.utils.chat_formatting import text_to_file

from ..abc import MixinMeta


class ChatExport(MixinMeta):
    @commands.command(name="exportchat")
    @commands.guildowner()
    @commands.bot_has_permissions(attach_files=True)
    async def export_chat(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = commands.CurrentChannel,
        limit: int = 50,
        tz_info: str = "UTC",
        military_time: bool = False,
    ):
        """
        Export chat history to an html file
        """

        async with ctx.typing():
            try:
                transcript = await chat_exporter.export(
                    channel=channel,
                    limit=limit,
                    tz_info=tz_info,
                    guild=ctx.guild,
                    bot=self.bot,
                    military_time=military_time,
                    fancy_times=True,
                    support_dev=False,
                )
            except AttributeError:
                transcript = None

            if transcript is None:
                return await ctx.send("Failed to export chat")

            file = text_to_file(transcript, filename=f"transcript-{channel.name}.html")
            msg = await ctx.send(file=file)
            txt = f"**[Click to View Export](https://mahto.id/chat-exporter?url={msg.attachments[0].url})**"
            await msg.edit(content=txt)
