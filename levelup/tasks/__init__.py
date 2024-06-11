from ..abc import CompositeMetaClass
from .weekly import WeeklyTask


class Tasks(WeeklyTask, metaclass=CompositeMetaClass):
    """
    Subclass all shared metaclassed parts of the cog

    This includes all task loops for LevelUp
    """

    def start_levelup_tasks(self):
        self.weekly_reset_check.start()

    def stop_levelup_tasks(self):
        self.weekly_reset_check.cancel()
