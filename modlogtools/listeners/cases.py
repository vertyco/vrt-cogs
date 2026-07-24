import logging

from redbot.core import commands, modlog

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.modlogtools.listeners.cases")


class CaseListeners(MixinMeta):
    @commands.Cog.listener()
    async def on_modlog_case_create(self, case: modlog.Case):
        if case.action_type != "warning":
            return
        try:
            await self.capture_warning_case(case)
        except Exception as e:
            log.error("Failed to capture warning case %s", case.case_number, exc_info=e)
