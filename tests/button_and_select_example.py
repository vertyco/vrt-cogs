import discord

from redbot.core import commands, Config, bank
from discord_components import Button, Select, SelectOption, ComponentsBot

class btest(commands.Cog):
    """
    Button test
    """
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot

    # make button
    @commands.command()
    async def button(self, ctx):
        await ctx.send("Buttons!", components=[Button(label="Button", custom_id="button1")])
        interaction = await self.bot.wait_for(
            "button_click", check=lambda inter: inter.custom_id == "button1"
        )
        await interaction.send(content="Button Clicked")


    # drop down menu
    @commands.command()
    async def select(self, ctx):
        await ctx.send(
            "Selects!",
            components=[
                Select(
                    placeholder="Select something!",
                    options=[
                        SelectOption(label="a", value="a"),
                        SelectOption(label="b", value="b"),
                    ],
                    custom_id="select1",
                )
            ],
        )

        interaction = await self.bot.wait_for(
            "select_option", check=lambda inter: inter.custom_id == "select1"
        )
        await interaction.send(content=f"{interaction.values[0]} selected!")