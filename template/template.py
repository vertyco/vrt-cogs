import discord
from redbot.core import commands, Config
# Importing a class
from .testing import test
from .buttons import buttonmenu, DEFAULT_BUTTON_CONTROLS
from dislash import (ActionRow,
                     Button,
                     ButtonStyle,
                     ResponseType,
                     InteractionClient,
                     SelectMenu,
                     SelectOption)


EMB = [
    discord.Embed(description="page 1"),
    discord.Embed(description="page 2"),
    discord.Embed(description="page 3"),
    discord.Embed(description="page 4"),
    discord.Embed(description="page 5"),
]


class Template(test, commands.Cog):
    """
    Some docstring saying what the cog is
    """
    __author__ = "Vertyco"
    __version__ = "Version No."

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.test_list = [1, 2, 3, 4, 5]

        # Dislash monkeypatch
        InteractionClient(bot)

    @commands.command(name="te")
    async def test_command(self, ctx):
        """This is a test command"""
        await self.test()


    @commands.command()
    async def rem(self, ctx, num):
        self.test_list.remove(int(num))

    async def aaa(self):
        print(self.test_list)

    @commands.command()
    async def bla(self, ctx):
        with open(f"{ctx.guild}.txt", "w") as file:
            file.write("lkdsjfkljdslfjdslkfj\nkjdslfjdlsk")
        with open(f"{ctx.guild}.txt", "rb") as file:
            embed = discord.Embed(description="ldksjfl")
            await ctx.send(embed=embed, file=discord.File(file, "test thing.txt"))

    @commands.command()
    async def butt(self, ctx):
        await buttonmenu(ctx, EMB, DEFAULT_BUTTON_CONTROLS)

    @commands.command()
    async def men(self, ctx):
        msg = await ctx.send(
            "This message has a select menu!",
            components=[
                SelectMenu(
                    custom_id="test",
                    placeholder="Choose an option",
                    max_values=1,
                    options=[
                        SelectOption("Option 1", "value 1"),
                        SelectOption("Option 2", "value 2"),
                        SelectOption("Option 3", "value 3")
                    ]
                )
            ]
        )

        def check(inter):
            return inter.author == ctx.author
        # Wait for a menu click under the message you've just sent
        inter = await msg.wait_for_dropdown(check)
        # Tell which options you received
        labels = [option.label for option in inter.select_menu.selected_options]
        values = [option.value for option in inter.select_menu.selected_options]
        await inter.reply(f"Your choices: {', '.join(labels)}")
        await ctx.send(values)


