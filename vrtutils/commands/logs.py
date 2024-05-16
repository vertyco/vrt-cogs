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
    async def scroll_logs(self, ctx: commands.Context, max_pages: int = 20):
        """View the bot's logs."""
        core = core_data_path()
        log_dir = core / "logs"
        logs: t.List[Path] = []
        for file in log_dir.iterdir():
            if re.match(r"latest(?:-part(?P<part>\d+))?\.log", file.name):
                logs.append(file)
        logs.sort(reverse=True)
        # Combine contents of all log files
        combined = "\n".join(log.read_text(encoding="utf-8", errors="ignore") for log in logs)
        split = [i for i in pagify(combined, page_length=1800)]
        split.reverse()
        split = split[:max_pages]
        pages = []
        for idx, chunk in enumerate(split):
            foot = f"Page {idx + 1}/{len(split)}"
            txt = f"{box(chunk, lang='python')}\n{foot}"
            pages.append(txt)
        await DynamicMenu(ctx.author, pages, ctx.channel).refresh()
