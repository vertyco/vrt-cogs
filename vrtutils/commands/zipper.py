import asyncio
import typing as t
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common.utils import get_attachments


class Zipper(MixinMeta):
    @commands.command(name="zip")
    @commands.is_owner()
    async def zip_file(self, ctx: commands.Context, *, archive_name: str = "archive.zip"):
        """
        zip a file or files
        """
        if not archive_name.endswith(".zip"):
            archive_name += ".zip"
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send("Please attach your files to the command or reply to a message with attachments")

        def zip_files(prepped: list) -> discord.File:
            zip_buffer = BytesIO()
            zip_buffer.name = archive_name
            with ZipFile(zip_buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as arc:
                for name, bytefile in prepped:
                    arc.writestr(
                        zinfo_or_arcname=name,
                        data=bytefile,
                        compress_type=ZIP_DEFLATED,
                        compresslevel=9,
                    )
            zip_buffer.seek(0)
            return discord.File(zip_buffer)

        async with ctx.typing():
            prepped = [(i.filename, await i.read()) for i in attachments]
            file = await asyncio.to_thread(zip_files, prepped)
            if file.__sizeof__() > ctx.guild.filesize_limit:
                return await ctx.send("ZIP file too large to send!")
            try:
                await ctx.send("Here is your zip file!", file=file)
            except discord.HTTPException:
                await ctx.send("File is too large!")

    @commands.command(name="unzip")
    @commands.is_owner()
    async def unzip_file(self, ctx: commands.Context):
        """
        Unzips a zip file and sends the extracted files in the channel
        """
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send("Please attach a zip file to the command or reply to a message with a zip file")

        def unzip_files(prepped: list) -> t.List[discord.File]:
            files = []
            for bytefile in prepped:
                with ZipFile(BytesIO(bytefile), "r") as arc:
                    for file_info in arc.infolist():
                        if file_info.is_dir():
                            continue
                        with arc.open(file_info) as extracted:
                            files.append(
                                discord.File(
                                    BytesIO(extracted.read()),
                                    filename=extracted.name,
                                )
                            )
            return files

        def group_files(files: list) -> t.List[t.List[discord.File]]:
            grouped_files = []
            total_size = 0
            current_group = []

            for file in files:
                file_size = file.__sizeof__()

                if total_size + file_size > ctx.guild.filesize_limit or len(current_group) == 9:
                    grouped_files.append(current_group)
                    current_group = []
                    total_size = 0

                current_group.append(file)
                total_size += file_size

            if current_group:
                grouped_files.append(current_group)

            return grouped_files

        async with ctx.typing():
            prepped = [await i.read() for i in attachments]
            files = await asyncio.to_thread(unzip_files, prepped)
            to_group = []
            for file in files:
                if file.__sizeof__() > ctx.guild.filesize_limit:
                    await ctx.send(f"File **{file.filename}** is too large to send!")
                    continue
                to_group.append(file)

            grouped = group_files(to_group)
            for file_list in grouped:
                names = ", ".join(f"`{i.filename}`" for i in file_list)
                try:
                    await ctx.send(names[:2000], files=file_list)
                except discord.HTTPException:
                    await ctx.send(f"Failed to dump the following files: {names}")
