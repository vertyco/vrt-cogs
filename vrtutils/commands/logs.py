import asyncio
import re
import typing as t
from pathlib import Path

from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common.dynamic_menu import DynamicMenu

LATEST_LOG_RE = re.compile(r"latest(?:-part(?P<part>\d+))?\.log")


class Logs(MixinMeta):
    @commands.command(name="logs")
    @commands.is_owner()
    async def scroll_logs(self, ctx: commands.Context):
        """View the bot's logs."""

        def _get_logs() -> t.List[str]:
            logs: t.List[Path] = []
            for file in (self.core / "logs").iterdir():
                if LATEST_LOG_RE.match(file.name):
                    logs.append(file)
            logs.sort(reverse=True)
            # Combine contents of all log files
            combined = "\n".join(log.read_text(encoding="utf-8", errors="ignore").strip() for log in logs)
            split = [i for i in pagify(combined, page_length=1800)]
            split.reverse()
            pages = []
            for idx, chunk in enumerate(split):
                foot = f"Page {idx + 1}/{len(split)}"
                txt = f"{box(chunk, lang='python')}\n{foot}"
                pages.append(txt)
            return pages

        pages = await asyncio.to_thread(_get_logs)
        await DynamicMenu(ctx.author, pages, ctx.channel, timeout=7200).refresh()
