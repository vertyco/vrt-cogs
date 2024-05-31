import asyncio
import re
import typing as t
from pathlib import Path

from redbot.core import commands
from redbot.core.data_manager import core_data_path
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common.dynamic_menu import DynamicMenu


class Logs(MixinMeta):
    @commands.command(name="logs")
    @commands.is_owner()
    async def scroll_logs(self, ctx: commands.Context, max_pages: int = 50):
        """View the bot's logs."""
        latest_re = re.compile(r"latest(?:-part(?P<part>\d+))?\.log")

        def _get_logs() -> t.List[str]:
            log_dir = core_data_path() / "logs"
            logs: t.List[Path] = []
            for file in log_dir.iterdir():
                if latest_re.match(file.name):
                    logs.append(file)
            logs.sort(reverse=True)
            # Combine contents of all log files
            combined = "\n".join(log.read_text(encoding="utf-8", errors="ignore") for log in logs)
            split = [i for i in pagify(combined, page_length=1800)]
            split = split[:max_pages]
            split.reverse()
            pages = []
            for idx, chunk in enumerate(split):
                foot = f"Page {idx + 1}/{len(split)}"
                txt = f"{box(chunk, lang='python')}\n{foot}"
                pages.append(txt)
            return pages

        pages = await asyncio.to_thread(_get_logs)
        await DynamicMenu(ctx.author, pages, ctx.channel, timeout=7200).refresh()
