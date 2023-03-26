import asyncio
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from time import monotonic

import discord
from pytube import Channel, Playlist, YouTube
from pytube.exceptions import VideoUnavailable
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number, humanize_timedelta
from redbot.core.utils.predicates import MessagePredicate

log = logging.getLogger("red.vrt.youtubedownloader")
_ = Translator("YouTubeDownloader", __file__)
DOWNLOADING = "https://i.imgur.com/l3p6EMX.gif"


def get_bar(progress, total, width: int = 20) -> str:
    ratio = progress / total
    bar = "█" * round(ratio * width) + "-" * round(width - (ratio * width))
    return f"|{bar}| {round(100 * ratio, 1)}%"


def fix_filename(name: str):
    bad_chars = ["?", "/", "\\", ":", '"', "<", ">", "|", "*"]
    for k in bad_chars:
        name = name.replace(k, "")
    return name


def download_stream(url: str) -> discord.File:
    yt = YouTube(url)
    stream = yt.streams.get_audio_only()
    buffer = BytesIO()
    name = fix_filename(yt.title)
    buffer.name = f"{name}.mp3"
    stream.stream_to_buffer(buffer)
    buffer.seek(0)
    file = discord.File(buffer, filename=buffer.name)
    return file


def download_local(url: str, path: str) -> None:
    yt = YouTube(url)
    name = fix_filename(yt.title)
    filename = f"{name}.mp4"
    if os.path.exists(f"{path}/{filename}"):
        return
    stream = yt.streams.get_audio_only()
    stream.download(output_path=path, filename=filename)


async def confirm(ctx: commands.Context):
    pred = MessagePredicate.yes_or_no(ctx)
    try:
        await ctx.bot.wait_for("message", check=pred, timeout=30)
    except asyncio.TimeoutError:
        return None
    else:
        return pred.result


@cog_i18n(_)
class YouTubeDownloader(commands.Cog):
    """
    Download YouTube videos to mp4 audio files!

    You can either have the files sent directly to Discord,
    or downloaded locally to a folder of your choosing.

    **Warning**
    Heavy usage of this cog may result in your bots ip getting suspended by YouTube,
    use at your own risk.
    """

    __author__ = "Vertyco"
    __version__ = "0.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        default_global = {"download_path": None, "downloaded": 0}
        self.config.register_global(**default_global)
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="youtube_downloader"
        )

    @commands.group(aliases=["youtubedownloader", "ytdl"])
    async def yt(self, ctx):
        """
        Download YouTube videos to mp4 audio files!

        You can either have the files sent directly to Discord,
        or downloaded locally to a folder of your choosing.

        **Warning**
        Heavy usage of this cog may result in your bots ip getting suspended by YouTube,
        use at your own risk.
        """

    @yt.command()
    @commands.is_owner()
    async def downloadpath(self, ctx, *, path: str):
        """Set your path for local downloads"""
        if not os.path.isdir(path) or not os.path.exists(path):
            return await ctx.send(_("That is not a valid path."))
        await self.config.download_path.set(path)
        await ctx.tick()

    @yt.command()
    @commands.is_owner()
    async def view(self, ctx):
        """View the current download path and total files downloaded"""
        path = await self.config.download_path()
        downloaded = await self.config.downloaded()
        em = discord.Embed(
            title=_("YouTube Downloader Settings"),
            description=_(
                f"`Path:       `{path}\n" f"`Downloaded: `{humanize_number(downloaded)}"
            ),
            color=ctx.author.color,
        )
        await ctx.send(embed=em)

    @yt.command()
    async def get(self, ctx, link: str):
        """Get an audio file from a YouTube link"""
        if "playlist" in link:
            return await ctx.send(
                _(
                    "The link you provided is for a playlist.\n"
                    "Please provide a valid link."
                )
            )
        async with ctx.typing():
            try:
                file = await self.bot.loop.run_in_executor(
                    self.executor, lambda: download_stream(link)
                )
            except (VideoUnavailable, KeyError):
                return await ctx.send(_("Failed to download YouTube video"))

        filesize = sys.getsizeof(file)
        allowedsize = ctx.guild.filesize_limit
        if filesize > allowedsize:
            return await ctx.send(_("Failed to download, file size too big to send."))

        text = _("Here is your mp3 file: ")
        await ctx.send(f"{text} `{file.filename}`", file=file)
        dl = await self.config.downloaded()
        await self.config.downloaded.set(dl + 1)

    @yt.command()
    async def multi(self, ctx, *, link: str):
        """
        Get multiple audio files from a list of links

        To include multiple links, separate them with a linebreak
        You may also include playlists
        """
        urls = link.split("\n")
        downloaded = 0
        failed = 0
        async with ctx.typing():
            for url in urls:
                if "playlist" in url:
                    try:
                        p = Playlist(url)
                    except VideoUnavailable:
                        failed += 1
                        continue
                    for purl in p.video_urls:
                        try:
                            file = await self.bot.loop.run_in_executor(
                                self.executor, lambda: download_stream(purl)
                            )
                        except (VideoUnavailable, KeyError):
                            failed += 1
                        except Exception as e:
                            log.error(f"mp3s download exception: {e}")
                            failed += 1

                        filesize = sys.getsizeof(file)
                        allowedsize = ctx.guild.filesize_limit
                        if filesize > allowedsize:
                            await ctx.send(
                                _(f"Skipping `{url}`\nFile size too big to send.")
                            )
                            failed += 1
                            continue
                        else:
                            await ctx.send(file.filename, file=file)
                            downloaded += 1
                else:
                    try:
                        file = await self.bot.loop.run_in_executor(
                            self.executor, lambda: download_stream(url)
                        )
                    except (VideoUnavailable, KeyError):
                        await ctx.send(_(f"Skipping `{url}`"))
                        failed += 1
                        continue

                filesize = sys.getsizeof(file)
                allowedsize = ctx.guild.filesize_limit
                if filesize > allowedsize:
                    await ctx.send(_(f"Skipping `{url}`\nFile size too big to send."))
                    failed += 1
                    continue
                else:
                    await ctx.send(file.filename, file=file)
                    downloaded += 1

        desc = ""
        if downloaded or failed:
            desc = box(_(f"Downloaded: {downloaded}\n" f"Failed:     {failed}"))
        text = _("Downloading Complete")
        embed = discord.Embed(
            description=f"**{text}**\n" f"{desc}", color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        if downloaded:
            dl = await self.config.downloaded()
            await self.config.downloaded.set(dl + downloaded)

    @yt.command()
    @commands.is_owner()
    async def playlist(self, ctx, folder_name: str, playlist_link: str):
        """Download all videos from a playlist to audio files"""
        if "playlist" not in playlist_link and "index" not in playlist_link:
            invalid = f"`{playlist_link}`" + _(" is not a valid playlist link.")
            return await ctx.send(invalid)
        color = ctx.author.color
        main_path = await self.config.download_path()
        msg = None
        if main_path is None or not os.path.exists(main_path):
            main_path = None
            text = (
                _(
                    "The download path is not set, would you like to use this cog's data folder instead? "
                )
                + "(y/n)"
            )
            em = discord.Embed(description=text, color=color)
            msg = await ctx.send(embed=em)
            yes = await confirm(ctx)
            if yes is not True:
                text = (
                    _("Download cancelled, please set a download path with ")
                    + f"`{ctx.prefix}yt downloadpath`"
                )
                em = discord.Embed(description=text, color=color)
                return await msg.edit(embed=em)
        if not main_path:
            main_path = cog_data_path(self)
        dirname = os.path.join(main_path, folder_name)
        if not os.path.exists(dirname):
            try:
                os.mkdir(dirname)
            except Exception as e:
                text = _("Failed to make directory")
                em = discord.Embed(description=f"{text}\n{box(str(e))}", color=color)
                if msg:
                    return await msg.edit(embed=em)
                else:
                    return await ctx.send(embed=em)
        try:
            p = Playlist(playlist_link)
        except Exception as e:
            text = _("Failed to parse ") + f"`{playlist_link}`"
            em = discord.Embed(description=f"{text}\n{box(str(e))}", color=color)
            if msg:
                return await msg.edit(embed=em)
            else:
                return await ctx.send(embed=em)

        count = p.length
        playlist_name = p.title
        text = (
            _(f"Found `{humanize_number(count)}` videos in the ")
            + f"**{playlist_name}** "
            + _("playlist, are you sure you want to download them all? ")
            + "(y/n)"
        )
        em = discord.Embed(description=text, color=color)
        if msg:
            await msg.edit(embed=em)
        else:
            msg = await ctx.send(embed=em)
        yes = await confirm(ctx)
        if yes is not True:
            text = _("Download cancelled")
            em = discord.Embed(description=text, color=color)
            return await msg.edit(embed=em)

        title = (
            _(f"Downloading {humanize_number(count)} videos from ")
            + f"{playlist_name}..."
        )
        downloaded = 0
        failed = 0
        index = 1
        start = monotonic()
        eta = None
        times = []
        async with ctx.typing():
            for url in p.video_urls:
                iter_start = monotonic()
                time_elapsed = humanize_timedelta(seconds=int(iter_start - start))

                if times:
                    avg_iter = int(sum(times) / len(times))
                    eta_raw = int((count - index) * avg_iter)
                    eta = humanize_timedelta(seconds=eta_raw)

                if eta:
                    prog = _(
                        f"`Progress: `{humanize_number(index)}/{humanize_number(count)}\n"
                        f"`Elapsed:  `{time_elapsed}\n"
                        f"`ETA:      `{eta}"
                    )
                else:
                    prog = _(
                        f"`Progress: `{humanize_number(index)}/{humanize_number(count)}"
                    )

                if index % 5 == 0 or index == count or index == 1:
                    bar = get_bar(index, count)
                    desc = f"{prog}\n{box(bar, lang='python')}"
                    em = discord.Embed(title=title, description=desc, color=color)
                    em.set_thumbnail(url=DOWNLOADING)
                    if msg:
                        await msg.edit(embed=em)
                    else:
                        msg = await ctx.send(embed=em)

                try:
                    await self.bot.loop.run_in_executor(
                        self.executor, lambda: download_local(url, dirname)
                    )
                    downloaded += 1
                except (VideoUnavailable, KeyError):
                    failed += 1
                except Exception as e:
                    log.error(f"Playlist download exception: {e}")
                    failed += 1

                index += 1

                iter_time = int(monotonic() - iter_start)
                if iter_time:
                    times.append(iter_time)

        unavailable = count - downloaded - failed
        em = discord.Embed(
            title=_("Download Complete"),
            description=_(
                f"Details\n"
                f"`Downloaded:  `{downloaded}\n"
                f"`Failed:      `{failed}\n"
                f"`Unavailable: `{unavailable}"
            ),
            color=discord.Color.green(),
        )
        em.add_field(name=_("Download Location"), value=box(dirname))
        await msg.edit(embed=em)
        if downloaded:
            dl = await self.config.downloaded()
            await self.config.downloaded.set(dl + downloaded)

    @yt.command()
    @commands.is_owner()
    async def channel(self, ctx, folder_name: str, channel_link: str):
        """Download all videos from a YouTube channel to audio files"""
        if "playlist" in channel_link or "index" in channel_link:
            invalid = f"`{channel_link}`" + _(" is not a valid channel link.")
            return await ctx.send(invalid)
        color = ctx.author.color
        main_path = await self.config.download_path()
        msg = None
        if main_path is None or not os.path.exists(main_path):
            main_path = None
            text = (
                _(
                    "The download path is not set, would you like to use this cog's data folder instead? "
                )
                + "(y/n)"
            )
            em = discord.Embed(description=text, color=color)
            msg = await ctx.send(embed=em)
            yes = await confirm(ctx)
            if yes is not True:
                text = (
                    _("Download cancelled, please set a download path with ")
                    + f"`{ctx.prefix}yt downloadpath`"
                )
                em = discord.Embed(description=text, color=color)
                return await msg.edit(embed=em)
        if not main_path:
            main_path = cog_data_path(self)
        dirname = os.path.join(main_path, folder_name)
        if not os.path.exists(dirname):
            try:
                os.mkdir(dirname)
            except Exception as e:
                text = _("Failed to make directory")
                em = discord.Embed(description=f"{text}\n{box(str(e))}", color=color)
                if msg:
                    return await msg.edit(embed=em)
                else:
                    return await ctx.send(embed=em)
        try:
            c = Channel(channel_link)
        except Exception as e:
            text = _("Failed to parse ") + f"`{channel_link}`"
            em = discord.Embed(description=f"{text}\n{box(str(e))}", color=color)
            if msg:
                return await msg.edit(embed=em)
            else:
                return await ctx.send(embed=em)

        channel_name = c.channel_name
        text = (
            _("Getting video count for ") + f"`{channel_name}`, " + _("please wait...")
        )
        em = discord.Embed(description=text, color=color)
        em.set_thumbnail(url=DOWNLOADING)
        if msg:
            await msg.edit(embed=em)
        else:
            msg = await ctx.send(embed=em)

        count = await self.bot.loop.run_in_executor(self.executor, lambda: len(c))
        text = (
            _(f"Found `{humanize_number(count)}` videos in the ")
            + f"**{channel_name}** "
            + _("channel, are you sure you want to download them all? ")
            + "(y/n)"
        )
        em = discord.Embed(description=text, color=color)
        await msg.edit(embed=em)
        yes = await confirm(ctx)
        if yes is not True:
            text = _("Download cancelled")
            em = discord.Embed(description=text, color=color)
            return await msg.edit(embed=em)

        title = (
            _(f"Downloading {humanize_number(count)} videos from ")
            + f"{channel_name}..."
        )
        downloaded = 0
        failed = 0
        index = 1
        start = monotonic()
        eta = None
        times = []
        async with ctx.typing():
            for url in c.video_urls:
                iter_start = monotonic()
                time_elapsed = humanize_timedelta(seconds=int(iter_start - start))

                if times:
                    avg_iter = int(sum(times) / len(times))
                    eta_raw = int((count - index) * avg_iter)
                    eta = humanize_timedelta(seconds=eta_raw)

                if eta:
                    prog = _(
                        f"`Progress: `{humanize_number(index)}/{humanize_number(count)}\n"
                        f"`Elapsed:  `{time_elapsed}\n"
                        f"`ETA:      `{eta}"
                    )
                else:
                    prog = _(
                        f"`Progress: `{humanize_number(index)}/{humanize_number(count)}"
                    )

                if index % 5 == 0 or index == count or index == 1:
                    bar = get_bar(index, count)
                    desc = f"{prog}\n{box(bar, lang='python')}"
                    em = discord.Embed(title=title, description=desc, color=color)
                    em.set_thumbnail(url=DOWNLOADING)
                    await msg.edit(embed=em)

                try:
                    await self.bot.loop.run_in_executor(
                        self.executor, lambda: download_local(url, dirname)
                    )
                    downloaded += 1
                except (VideoUnavailable, KeyError):
                    failed += 1
                except Exception as e:
                    log.error(f"Channel download exception: {e}")
                    failed += 1

                index += 1

                iter_time = int(monotonic() - iter_start)
                if iter_time:
                    times.append(iter_time)

        unavailable = count - downloaded - failed
        em = discord.Embed(
            title=_("Download Complete"),
            description=_(
                f"Details\n"
                f"`Downloaded:   `{downloaded}\n"
                f"`Failed:       `{failed}\n"
                f"`Unavailable:  `{unavailable}\n"
                f"`Time Elapsed: `{time_elapsed}"
            ),
            color=discord.Color.green(),
        )
        em.add_field(name=_("Download Location"), value=box(dirname))
        await msg.edit(embed=em)
        if downloaded:
            dl = await self.config.downloaded()
            await self.config.downloaded.set(dl + downloaded)
