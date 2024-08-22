import asyncio
import functools
import logging
import math
import random
import traceback
from io import BytesIO
from typing import List, Optional

import discord
from PIL import Image, UnidentifiedImageError
from redbot.core import Config, bank, commands
from redbot.core.bot import Red
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_number,
    humanize_timedelta,
    pagify,
)
from tabulate import tabulate

from .defaults import defaults
from .utils import PixlGrids, delete, exe, get_content_from_url

log = logging.getLogger("red.vrt.pixl")
dpy2 = True if discord.version_info.major >= 2 else False
if dpy2:
    InteractionClient = None
    from discord import Interaction

    from .menu import DEFAULT_CONTROLS, MenuView, menu
else:
    from dislash import Interaction, InteractionClient  # type: ignore

    from .dmenu import DEFAULT_CONTROLS, MenuView, menu


class Pixl(commands.Cog):
    """
    Guess pictures for points

    Pixl is an image guessing game that reveals parts of an image over time while users race to guess the correct answer first.

    **Images are split up into 192 blocks and slowly revealed over time.**
    The score of the game is based on how many blocks are left when the image is guessed.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.3.7"

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if InteractionClient:
            InteractionClient(bot, sync_commands=False)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=117, force_registration=True)
        default_guild = {
            "images": [],  # Images added by the guild
            "time_limit": 300,  # Time limit before image is revealed and game is over
            "blocks_to_reveal": 2,  # Amount of blocks to reveal after each delay
            "min_participants": 1,  # Minimum participants to reward credits
            "currency_ratio": 0.0,  # Points x Ratio = Credit reward
            "show_answer": True,  # Show the answer after game over
            "use_global": True,  # Use global images added by bot owner
            "use_default": True,  # Use default images
        }
        default_global = {
            "images": [],  # Images added by bot owner
            "delay": 5,  # Delay between block reveals
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.config.register_member(wins=0, games=0, score=0)

        self.active = set()

    @commands.command(name="pixlboard", aliases=["pixlb", "pixelb", "pixlelb", "pixleaderboard"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def pixl_leaderboard(self, ctx: commands.Context, show_global: Optional[bool]):
        """View the Pixl leaderboard!

        **Arguments**
        `show_global`: show the global leaderboard

        example: `[p]pixlb true`
        """
        if show_global:
            title = "Global Pixlboard!"
            all_users = {}
            data = await self.config.all_members()
            for gid, users in data.items():
                guild = ctx.bot.get_guild(gid)
                if not guild:
                    continue
                for uid, userdata in users.items():
                    user = guild.get_member(uid)
                    if not user:
                        continue
                    if user in all_users:
                        for k, v in userdata.items():
                            all_users[user][k] += v
                    else:
                        all_users[user] = userdata
        else:
            title = "Pixlboard!"
            all_users = {}
            users = await self.config.all_members(ctx.guild)
            for uid, userdata in users.items():
                user = ctx.guild.get_member(uid)
                if not user:
                    continue
                all_users[user] = userdata

        if not all_users:
            return await ctx.send(f"There are no users saved yet, start a game with `{ctx.clean_prefix}pixl`")
        sorted_users = sorted(all_users.items(), key=lambda x: x[1]["score"], reverse=True)
        you = None
        for num, i in enumerate(sorted_users):
            if i[0] == ctx.author:
                you = f"You: {num + 1}/{len(sorted_users)}"
                break

        embeds = []
        pages = math.ceil(len(sorted_users) / 10)
        start = 0
        stop = 10
        for p in range(pages):
            if stop > len(sorted_users):
                stop = len(sorted_users)
            table = []
            for i in range(start, stop):
                place = i + 1
                user: discord.Member = sorted_users[i][0]
                data = sorted_users[i][1]
                table.append([place, user.name, data["score"], data["wins"], data["games"]])
            board = tabulate(
                tabular_data=table,
                headers=["#", "Name", "Score", "Wins", "Games"],
                numalign="left",
                stralign="left",
            )
            embed = discord.Embed(title=title, description=box(board, "py"), color=ctx.author.color)
            foot = f"Page {p + 1}/{pages}"
            if you:
                foot += f" | {you}"
            embed.set_footer(text=foot)
            embeds.append(embed)
            start += 10
            stop += 10
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command(name="pixl", aliases=["pixle", "pixlguess", "pixelguess", "pixleguess"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def pixl(self, ctx: commands.Context):
        """
        Start a Pixl game!
        Guess the image as it is slowly revealed
        """
        cid = ctx.channel.id
        uid = ctx.author.id
        if cid in self.active:
            return await ctx.send("There is already a Pixl game going on in this channel")
        elif uid in self.active:
            return await ctx.send("You already have a Pixl game going on")
        self.active.add(cid)
        self.active.add(uid)
        try:
            await self.start_game(ctx)
        finally:
            self.active.discard(cid)
            self.active.discard(uid)

    async def start_game(self, ctx: commands.Context):
        conf = await self.config.guild(ctx.guild).all()
        delay = await self.config.delay()

        to_use = conf["images"]
        if conf["use_global"]:
            global_images = await self.config.images()
            to_use.extend(global_images)
        if conf["use_default"] or len(to_use) == 0:
            to_use.extend(defaults)

        tries = 0
        cant_get = []
        while tries < 3:
            tries += 1
            choice = random.choice(to_use)
            url = choice["url"]
            correct = choice["answers"]
            imgbytes = await get_content_from_url(url)
            if not imgbytes:
                cant_get.append(url)
                continue
            try:
                game_image = await exe(functools.partial(Image.open, BytesIO(imgbytes)))
            except UnidentifiedImageError:
                cant_get.append(url)
                continue
            break
        else:
            invalid = "\n".join(cant_get)
            return await ctx.send(f"Game prep failed 3 times in a row\n\nThese urls were invalid\n{box(invalid)}")

        if cant_get:
            invalid = "\n".join(cant_get)
            await ctx.send(f"Some images failed during prep\n{box(invalid)}")

        game = PixlGrids(ctx, game_image, correct, conf["blocks_to_reveal"], conf["time_limit"])
        msg = None
        embed = discord.Embed(
            title="Pixl Guess",
            description=f"Guess the image before it's fully revealed!\nTime runs out {game.time_left}",
            color=discord.Color.random(),
        )
        try:
            async with ctx.typing():
                async for image in game:
                    att = f"attachment://{image.filename}"
                    embed.set_image(url=att)
                    if msg is None:
                        msg = await ctx.send(embed=embed, file=image)
                    else:
                        asyncio.create_task(delete(msg))
                        msg = await ctx.send(embed=embed, file=image)
                    await asyncio.sleep(delay)
        except Exception:
            return await ctx.send(
                f"Something went wrong during the game!\n"
                f"Image: `{correct[0]} - {url}`\n"
                f"{box(traceback.format_exc(), 'py')}"
            )
        finally:
            game.data["in_progress"] = False

        winner = game.winner
        participants = len(game.data["participants"])
        points = len(game.to_chop)
        shown = 192 - points
        reward = round(points * conf["currency_ratio"])
        min_p = conf["min_participants"]

        final = await game.get_result()
        att = f"attachment://{final.filename}"
        thumb = None
        if winner:  # Chicken dinner
            thumb = (winner.display_avatar.url) if dpy2 else winner.avatar_url
            title = "Winner!"
            desc = f"{winner.name} guessed correctly after {shown} blocks!\n" f"`Points Awarded:  `{points}\n"
            if participants >= min_p and reward:
                desc += f"`Credits Awarded: `{humanize_number(reward)}"
            color = winner.color
        else:
            title = "Game Over!"
            if points > 0:  # Time ran out
                desc = "Nobody guessed before time ran out!"
            else:  # Picture was completed
                desc = "Nobody guessed before the picture was finished!"
            color = discord.Color.red()
        if conf["show_answer"]:
            desc += f"\nCorrect answer: ||{correct[0]}||"
        embed = discord.Embed(
            title=title,
            description=desc,
            color=color,
        )
        embed.set_image(url=att)
        if participants == 1:
            embed.set_footer(text="There was 1 participant")
        else:
            embed.set_footer(text=f"There were {participants} participants")
        if thumb:
            embed.set_thumbnail(url=thumb)

        asyncio.create_task(delete(msg))
        if winner:
            await ctx.send(winner.mention, embed=embed, file=final)
        else:
            await ctx.send(embed=embed, file=final)

        if winner:
            if reward and participants >= min_p:
                try:
                    await bank.deposit_credits(winner, reward)
                except BalanceTooHigh as e:
                    await bank.set_balance(winner, e.max_balance)
        players = list(game.data["participants"])
        for person in players:
            if person.bot:
                continue
            stats = await self.config.member(person).all()
            if winner:
                if person.id == winner.id:
                    stats["wins"] += 1
                    stats["score"] += points
            stats["games"] += 1
            await self.config.member(person).set(stats)

    @commands.group(name="pixlset", aliases=["pixelset", "pixleset"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def pixlset(self, ctx: commands.Context):
        """Configure the Pixl game"""
        pass

    @pixlset.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """View the current settings"""
        conf = await self.config.guild(ctx.guild).all()
        users = len(await self.config.all_members(ctx.guild))
        desc = (
            f"`Users Saved:    `{users}\n"
            f"`Time Limit:     `{conf['time_limit']}s\n"
            f"`Blocks:         `{conf['blocks_to_reveal']} per reveal\n"
            f"`Participants:   `{conf['min_participants']} minimum\n"
            f"`Currency Ratio: `{conf['currency_ratio']}x\n"
            f"`Show Answer:    `{conf['show_answer']}\n"
            f"Delay between blocks is {await self.config.delay()} seconds"
        )
        # If the timeout is faster than the amount of blocks could be revealed at that delay, calculate how many blocks would be left at game end
        if conf["time_limit"] < (conf["blocks_to_reveal"] * await self.config.delay()):
            blocks = conf["blocks_to_reveal"] - (conf["time_limit"] // await self.config.delay())
            desc += f"\n`Blocks Remaining: `{blocks} at game timeout"
        embed = discord.Embed(title="Pixl Settings", description=desc, color=ctx.author.color)
        global_images = await self.config.images()
        guild_images = conf["images"]
        embed.add_field(
            name="Images",
            value=f"`Saved in this guild: `{len(guild_images)}\n"
            f"`Saved globally:      `{len(global_images)} ({'enabled' if conf['use_global'] else 'disabled'})\n"
            f"`Default Images:      `{len(defaults)} ({'enabled' if conf['use_default'] else 'disabled'})",
        )
        await ctx.send(embed=embed)

    @pixlset.command(name="timelimit")
    async def set_timelimit(self, ctx: commands.Context, seconds: int):
        """Set the time limit for Pixl games"""
        if seconds < 10:
            return await ctx.send("Uhh that's a little quick, try more than 10 seconds...")
        async with ctx.typing():
            await self.config.guild(ctx.guild).time_limit.set(seconds)
            await ctx.send(f"Time limit has been set to {humanize_timedelta(seconds=seconds)}")

    @pixlset.command(name="blocks")
    async def set_blocks(self, ctx: commands.Context, amount: int):
        """Set the amount of blocks to reveal after each delay"""
        if amount >= 192 or amount < 1:
            return await ctx.send("The amount of blocks revealed at one time must be at least 1 but less than 192")
        async with ctx.typing():
            await self.config.guild(ctx.guild).blocks_to_reveal.set(amount)
            await ctx.send(f"The amount of blocks revealed after each delay has been set to {amount}")

    @pixlset.command(name="participants")
    async def set_participants(self, ctx: commands.Context, amount: int):
        """Set the minimum amount of participants for the game to reward users credits"""
        if amount < 1:
            return await ctx.send("Minimum participants must be greater than 0...")
        async with ctx.typing():
            await self.config.guild(ctx.guild).min_participants.set(amount)
            await ctx.send(f"The minimum participants needed for rewards has been set to {amount}")

    @pixlset.command(name="ratio")
    async def set_ratio(self, ctx: commands.Context, ratio: float):
        """
        Set the point to credit conversion ratio (points x ratio = credit reward)
        Points are calculated based on how many hidden blocks are left at the end of the game

        Ratio can be a decimal
        Set to 0 to disable credit rewards
        """
        if ratio < 0:
            return await ctx.send("Ratio needs to be greater than zero")
        async with ctx.typing():
            await self.config.guild(ctx.guild).currency_ratio.set(float(ratio))
            await ctx.send(f"The point to credit conversion ratio has been set to {ratio}")

    @pixlset.command(name="showanswer")
    async def toggle_show(self, ctx: commands.Context):
        """(Toggle) Showing the answer after a game over"""
        toggle = await self.config.guild(ctx.guild).show_answer()
        if toggle:
            await ctx.send("I will no longer show the answer on a game over")
            await self.config.guild(ctx.guild).show_answer.set(False)
        else:
            await ctx.send("I will now show the answer on a game over")
            await self.config.guild(ctx.guild).show_answer.set(True)

    @pixlset.command(name="useglobal")
    async def toggle_global(self, ctx: commands.Context):
        """(Toggle) Whether to use global images in this guild"""
        toggle = await self.config.guild(ctx.guild).use_global()
        if toggle:
            await ctx.send("I will no longer show global images in this guild")
            await self.config.guild(ctx.guild).use_global.set(False)
        else:
            await ctx.send("I will now show global images in this guild")
            await self.config.guild(ctx.guild).use_global.set(True)

    @pixlset.command(name="usedefault")
    async def toggle_default(self, ctx: commands.Context):
        """(Toggle) Whether to use the default hardcoded images in this guild"""
        toggle = await self.config.guild(ctx.guild).use_default()
        if toggle:
            await ctx.send("I will no longer show default images in this guild")
            await self.config.guild(ctx.guild).use_default.set(False)
        else:
            await ctx.send("I will now show default images in this guild")
            await self.config.guild(ctx.guild).use_default.set(True)

    @pixlset.command(name="delay")
    @commands.is_owner()
    async def set_game_delay(self, ctx: commands.Context, seconds: int):
        """
        (Owner Only)Set the delay between block reveals

        **Warning**
        Setting this too low may hit rate limits, default is 5 seconds.
        """
        if seconds < 2:
            return await ctx.send("Delay must be at least 2 seconds")
        async with ctx.typing():
            await self.config.delay.set(seconds)
            await ctx.send(f"Game delay has been set to {humanize_timedelta(seconds=seconds)}")

    @pixlset.group(name="image")
    async def image(self, ctx: commands.Context):
        """Add/Remove images"""
        pass

    @image.command(name="viewdefault")
    @commands.bot_has_permissions(embed_links=True)
    async def view_default_images(self, ctx: commands.Context):
        """View the default images"""
        await self.image_menu(ctx, defaults, "Default Images")

    @image.command(name="viewglobal")
    @commands.bot_has_permissions(embed_links=True)
    async def view_global_images(self, ctx: commands.Context):
        """View the global images"""
        images = await self.config.images()
        if not images or len(images) < 1:
            return await ctx.send("There are no global images to view")
        await self.image_menu(ctx, images, "Global Images")

    @image.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_images(self, ctx: commands.Context):
        """View the guild images"""
        images = await self.config.guild(ctx.guild).images()
        if not images or len(images) < 1:
            return await ctx.send("There are no guild images to view")
        await self.image_menu(ctx, images, "Guild Images")

    @image.command(name="testdefault", hidden=True)
    @commands.is_owner()
    async def test_defaults(self, ctx: commands.Context):
        """Test the default images to ensure they are valid urls"""
        async with ctx.typing():
            good, bad = await self.test_images(defaults)
            if bad:
                txt = "\n".join(bad)
                await ctx.send(f"The following urls are bad!\n{txt}")
            await ctx.send(f"Testing complete.\n`Good: {len(good)} | Bad: {len(bad)}`")

    @image.command(name="testglobal")
    @commands.is_owner()
    async def test_global(self, ctx: commands.Context):
        """Test the global images to ensure they are valid urls"""
        async with ctx.typing():
            global_images = await self.config.images()
            good, bad = await self.test_images(global_images)
            if bad:
                txt = "\n".join(bad)
                await ctx.send(f"The following urls are bad!\n{txt}")
            await ctx.send(f"Testing complete.\n`Good: {len(good)} | Bad: {len(bad)}`")

    @image.command(name="testguild")
    async def test_guild(self, ctx: commands.Context):
        """Test the guild images to ensure they are valid urls"""
        async with ctx.typing():
            guild_images = await self.config.guild(ctx.guild).images()
            good, bad = await self.test_images(guild_images)
            if bad:
                txt = "\n".join(bad)
                await ctx.send(f"The following urls are bad!\n{txt}")
            await ctx.send(f"Testing complete.\n`Good: {len(good)} | Bad: {len(bad)}`")

    @image.command(name="addglobal")
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def add_global_image(self, ctx: commands.Context, url: Optional[str], *, answers: Optional[str]):
        """
        Add a global image for all guilds to use

        **Arguments**
        `url:     `the url of the image
        `answers: `a list of possible answers separated by a comma

        **Alternative**
        If args are left blank, a text file can be uploaded with the following format for bulk image adding.
        Each line starts with the url followed by all the possible correct answers separated by a comma

        Example: `url, answer, answer, answer...`
        ```
        https://some_url.com/example.png, answer1, answer two, another answer
        https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer
        ```
        """
        global_images = await self.config.images()
        async with ctx.typing():
            if any([not url, not answers]):  # Check for attachments
                to_add = []
                failed = []
                embeds = []
                attachments = self.get_attachments(ctx)
                if not attachments:
                    return await ctx.send(
                        f"If you do not provide any arguments with this command then you must attach a text file.\n"
                        f"Type `{ctx.clean_prefix}help pixlset image addglobal` for more info."
                    )
                file = attachments[0]
                if not file.filename.endswith(".txt"):
                    return await ctx.send("This does not look like a `.txt` file!")

                text = (await file.read()).decode("utf-8").strip()
                lines = [line.strip() for line in text.split("\n")]
                for index, line in enumerate(lines):
                    if not line:  # Skip empty lines
                        continue
                    parts = [p.strip().lower() for p in line.split(",") if p.strip()]
                    if len(parts) < 2:
                        failed.append(f"Line {index + 1}(Invalid Format): {line}")
                        continue
                    url = parts.pop(0)
                    if any([g["url"] == url for g in global_images]):
                        failed.append(f"Line {index + 1}(Already Exists): {line}")
                        continue
                    image = await get_content_from_url(url)
                    if not image:
                        failed.append(f"Line {index + 1}(Invalid URL): {line}")
                        continue
                    answers = parts
                    to_add.append({"url": url, "answers": answers})

                added = len(to_add)
                for index, i in enumerate(to_add):
                    if index == 4:
                        break
                    embed = discord.Embed(
                        description=f"{added} Images Added!",
                        color=ctx.author.color,
                        url="https://vertyco.net",
                    ).set_image(url=i["url"])
                    if added > 4 and dpy2:
                        embed.set_footer(text="Showing first 4 images in the list")
                    embeds.append(embed)

                async with self.config.images() as images:
                    images.extend(to_add)

                if failed:
                    txt = "\n".join(failed)
                    await ctx.send("The following lines failed!")
                    for p in pagify(txt, page_length=2000):
                        await ctx.send(box(p))
                if not to_add:
                    return await ctx.send("There were no valid images that could be added!")
                await ctx.send(embeds=embeds) if dpy2 else await ctx.send(embed=embeds[0])
            else:
                if any([g["url"] == url for g in global_images]):
                    return await ctx.send("That global image url already exists!")
                image = await get_content_from_url(url)
                if not image:
                    return await ctx.send("I am unable to pull this image to use, please try another one")
                answers = [a.strip().lower() for a in answers.split(",")]
                async with self.config.images() as images:
                    images.append({"url": url, "answers": answers})
                embed = discord.Embed(
                    title="Global Image Added",
                    description=f"Answers: `{humanize_list(answers)}`",
                    color=ctx.author.color,
                )
                embed.set_image(url=url)
                await ctx.send(embed=embed)

    @image.command(name="add")
    @commands.bot_has_permissions(embed_links=True)
    async def add_image(self, ctx: commands.Context, url: Optional[str], *, answers: Optional[str]):
        """
        Add an image for your guild to use

        **Arguments**
        `url:     `the url of the image
        `answers: `a list of possible answers separated by a comma

        **Alternative**
        If args are left blank, a text file can be uploaded with the following format for bulk image adding.
        Each line starts with the url followed by all the possible correct answers separated by a comma

        Example: `url, answer, answer, answer...`
        ```
        https://some_url.com/example.png, answer1, answer two, another answer
        https://yet_another_url.com/another_example.jpg, answer one, answer 2, another answer
        ```
        """
        guild_images = await self.config.guild(ctx.guild).images()
        async with ctx.typing():
            if any([not url, not answers]):
                to_add = []
                failed = []
                embeds = []
                attachments = self.get_attachments(ctx)
                if not attachments:
                    return await ctx.send(
                        f"If you do not provide any arguments with this command then you must attach a text file.\n"
                        f"Type `{ctx.clean_prefix}help pixlset image add` for more info."
                    )
                file = attachments[0]
                if not file.filename.endswith(".txt"):
                    return await ctx.send("This does not look like a `.txt` file!")
                text = (await file.read()).decode("utf-8").strip()
                lines = [line.strip() for line in text.split("\n")]
                for i, line in enumerate(lines):
                    if not line:  # Skip empty lines
                        continue
                    parts = [p.strip().lower() for p in line.split(",") if p.strip()]
                    if len(parts) < 2:
                        failed.append(f"Line {i + 1}(Invalid Format): {line}")
                        continue
                    url = parts.pop(0)
                    if any([g["url"] == url for g in guild_images]):
                        failed.append(f"Line {i + 1}(Already Exists): {line}")
                        continue
                    image = await get_content_from_url(url)
                    if not image:
                        failed.append(f"Line {i + 1}(Invalid URL): {line}")
                        continue
                    answers = parts
                    to_add.append({"url": url, "answers": answers})
                added = len(to_add)
                for index, i in enumerate(to_add):
                    if index == 4:
                        break
                    embed = discord.Embed(
                        description=f"{added} Images Added!",
                        color=ctx.author.color,
                        url="https://vertyco.net",
                    ).set_image(url=i["url"])
                    if added > 4 and dpy2:
                        embed.set_footer(text="Showing first 4 images in the list")
                    embeds.append(embed)
                async with self.config.guild(ctx.guild).images() as images:
                    images.extend(to_add)
                if failed:
                    txt = "\n".join(failed)
                    await ctx.send("The following lines failed!")
                    for p in pagify(txt, page_length=2000):
                        await ctx.send(box(p))
                if not to_add:
                    return await ctx.send("There were no valid images that could be added!")
                await ctx.send(embeds=embeds) if dpy2 else await ctx.send(embed=embeds[0])
            else:
                if any([g["url"] == url for g in guild_images]):
                    return await ctx.send("That guild image url already exists!")
                image = await get_content_from_url(url)
                if not image:
                    return await ctx.send("I am unable to pull this image to use, please try another one")
                answers = [a.strip().lower() for a in answers.split(",")]
                async with self.config.guild(ctx.guild).images() as images:
                    images.append({"url": url, "answers": answers})
                embed = discord.Embed(
                    title="Image Added",
                    description=f"Answers: `{humanize_list(answers)}`",
                    color=ctx.author.color,
                )
                embed.set_image(url=url)
                await ctx.send(embed=embed)

    # -/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/ METHODS -/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/
    async def image_menu(
        self,
        ctx: commands.Context,
        images: list,
        title: str,
        message: discord.Message = None,
        page: int = 0,
    ):
        embeds = []
        pages = len(images)
        for num, i in enumerate(images):
            embed = discord.Embed(
                title=title,
                description=f"Valid Answers\n{box(humanize_list(i['answers']))}",
                color=ctx.author.color,
            )
            embed.set_image(url=i["url"])
            embed.set_footer(text=f"Page {num + 1}/{pages}")
            embeds.append(embed)

        con = DEFAULT_CONTROLS.copy()
        # If global, only show delete button to bot owner
        if ("global" in title.lower() and ctx.author.id in self.bot.owner_ids) or "guild" in title.lower():
            con["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_image
            con["\N{MEMO}"] = self.edit_image
        await menu(ctx, embeds, con, message=message, page=page)

    async def delete_image(self, instance: MenuView, interaction: Interaction):
        embed: discord.Embed = instance.pages[instance.page]
        title = embed.title
        conf = self.config if "global" in title.lower() else self.config.guild(instance.ctx.guild)
        async with conf.images() as images:
            del images[instance.page]
        del instance.pages[instance.page]

        images = await conf.images()
        if not images:
            await instance.respond(
                interaction,
                f"Image with url `{embed.image.url}` has been deleted. There are no more images.",
            )
            return await instance.message.delete()
        else:
            await instance.respond(interaction, f"Image with url `{embed.image.url}` has been deleted")
        page = (instance.page or 0) - 1
        page %= len(instance.pages)
        await self.image_menu(instance.ctx, images, title, message=instance.message, page=page)

    async def edit_image(self, instance: MenuView, interaction: Interaction):
        embed: discord.Embed = instance.pages[instance.page]
        title = embed.title
        conf = self.config if "global" in title.lower() else self.config.guild(instance.ctx.guild)
        await instance.respond(
            interaction,
            "Type the new answers for this image below, separated by commas",
        )

        def check(message: discord.Message):
            return message.author == instance.ctx.author and message.channel == instance.ctx.channel

        fs = [asyncio.ensure_future(instance.ctx.bot.wait_for("message", check=check))]
        done, pending = await asyncio.wait(fs, timeout=120)
        [task.cancel() for task in pending]
        reply = done.pop().result() if len(done) > 0 else None
        if not reply:
            await instance.ctx.send("Image answer editing cancelled")
            return await menu(
                instance.ctx,
                instance.pages,
                instance.controls,
                message=instance.message,
                page=instance.page,
            )
        elif reply.content == "cancel":
            await instance.ctx.send("Image answer editing cancelled")
            return await menu(
                instance.ctx,
                instance.pages,
                instance.controls,
                message=instance.message,
                page=instance.page,
            )
        answers = [i.strip().lower() for i in reply.content.split(",") if i.strip().lower()]
        if not answers:
            await instance.ctx.send("No answers found, image answer editing cancelled")
            return await menu(
                instance.ctx,
                instance.pages,
                instance.controls,
                message=instance.message,
                page=instance.page,
            )
        async with conf.images() as images:
            images[instance.page]["answers"] = answers

        await instance.ctx.send("Answers have been modified for this image!", delete_after=6)
        images = await conf.images()
        await self.image_menu(instance.ctx, images, title, message=instance.message, page=instance.page)

    @staticmethod
    def get_attachments(ctx: commands.Context) -> List[discord.Attachment]:
        """Get all attachments from context"""
        content = []
        if ctx.message.attachments:
            atchmts = [a for a in ctx.message.attachments]
            content.extend(atchmts)
        if hasattr(ctx.message, "reference"):
            try:
                atchmts = [a for a in ctx.message.reference.resolved.attachments]
                content.extend(atchmts)
            except AttributeError:
                pass
        return content

    @staticmethod
    async def test_images(images: list):
        good = []
        bad = []

        async def check(img):
            bytefile = await get_content_from_url(img["url"], timeout=10)
            if not bytefile:
                bad.append(f"(Bad URL)`{img['answers'][0]}: {img['url']}`")
                return
            try:
                partial = functools.partial(Image.open, BytesIO(bytefile))
                await exe(partial)
            except UnidentifiedImageError:
                bad.append(f"(Bad Image)`{img['answers'][0]}: {img['url']}`")
                return
            good.append(img["url"])

        tasks = [check(i) for i in images]
        await asyncio.gather(*tasks)
        return good, bad
