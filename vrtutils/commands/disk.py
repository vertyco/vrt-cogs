import asyncio
from concurrent.futures import ThreadPoolExecutor

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from ..common.diskspeed import get_disk_speed


class DiskBench(MixinMeta):
    @commands.command(aliases=["diskbench"])
    @commands.is_owner()
    async def diskspeed(self, ctx: commands.Context):
        """
        Get disk R/W performance for the server your bot is on

        The results of this test may vary, Python isn't fast enough for this kind of byte-by-byte writing,
        and the file buffering and similar adds too much overhead.
        Still this can give a good idea of where the bot is at I/O wise.
        """

        def diskembed(data: dict) -> discord.Embed:
            if data["write5"] != "Waiting..." and data["write5"] != "Running...":
                embed = discord.Embed(title="Disk I/O", color=discord.Color.green())
                embed.description = "Disk Speed Check COMPLETE"
            else:
                embed = discord.Embed(title="Disk I/O", color=ctx.author.color)
                embed.description = "Running Disk Speed Check"
            first = f"Write: {data['write1']}\n" f"Read:  {data['read1']}"
            embed.add_field(
                name="128 blocks of 1048576 bytes (128MB)",
                value=box(first, lang="python"),
                inline=False,
            )
            second = f"Write: {data['write2']}\n" f"Read:  {data['read2']}"
            embed.add_field(
                name="128 blocks of 2097152 bytes (256MB)",
                value=box(second, lang="python"),
                inline=False,
            )
            third = f"Write: {data['write3']}\n" f"Read:  {data['read3']}"
            embed.add_field(
                name="256 blocks of 1048576 bytes (256MB)",
                value=box(third, lang="python"),
                inline=False,
            )
            fourth = f"Write: {data['write4']}\n" f"Read:  {data['read4']}"
            embed.add_field(
                name="256 blocks of 2097152 bytes (512MB)",
                value=box(fourth, lang="python"),
                inline=False,
            )
            fifth = f"Write: {data['write5']}\n" f"Read:  {data['read5']}"
            embed.add_field(
                name="256 blocks of 4194304 bytes (1GB)",
                value=box(fifth, lang="python"),
                inline=False,
            )
            return embed

        results = {
            "write1": "Running...",
            "read1": "Running...",
            "write2": "Waiting...",
            "read2": "Waiting...",
            "write3": "Waiting...",
            "read3": "Waiting...",
            "write4": "Waiting...",
            "read4": "Waiting...",
            "write5": "Waiting...",
            "read5": "Waiting...",
        }
        msg = None
        for i in range(6):
            stage = i + 1
            em = diskembed(results)
            if not msg:
                msg = await ctx.send(embed=em)
            else:
                await msg.edit(embed=em)
            count = 128
            size = 1048576
            if stage == 2:
                count = 128
                size = 2097152
            elif stage == 3:
                count = 256
                size = 1048576
            elif stage == 4:
                count = 256
                size = 2097152
            elif stage == 6:
                count = 256
                size = 4194304
            res = await self.run_disk_speed(block_count=count, block_size=size, passes=3)
            write = f"{humanize_number(round(res['write'], 2))}MB/s"
            read = f"{humanize_number(round(res['read'], 2))}MB/s"
            results[f"write{stage}"] = write
            results[f"read{stage}"] = read
            if f"write{stage + 1}" in results:
                results[f"write{stage + 1}"] = "Running..."
                results[f"read{stage + 1}"] = "Running..."
            await asyncio.sleep(1)

    async def run_disk_speed(
        self,
        block_count: int = 128,
        block_size: int = 1048576,
        passes: int = 1,
    ) -> dict:
        reads = []
        writes = []
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = [
                self.bot.loop.run_in_executor(
                    pool,
                    lambda: get_disk_speed(self.path, block_count, block_size),
                )
                for _ in range(passes)
            ]
            results = await asyncio.gather(*futures)
            for i in results:
                reads.append(i["read"])
                writes.append(i["write"])
        results = {
            "read": sum(reads) / len(reads),
            "write": sum(writes) / len(writes),
        }
        return results
