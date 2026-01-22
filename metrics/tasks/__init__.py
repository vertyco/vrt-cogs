# Task loops can be defined here
from ..abc import CompositeMetaClass
from .snapshot import Snapshot


class TaskLoops(Snapshot, metaclass=CompositeMetaClass):
    """
    Subclass all task loops in this directory so you can import this single task loop class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """

    def start_tasks(self) -> None:
        if not self.economy_snapshot_task.is_running():
            self.economy_snapshot_task.start()
        if not self.member_snapshot_task.is_running():
            self.member_snapshot_task.start()
        if not self.performance_snapshot_task.is_running():
            self.performance_snapshot_task.start()

    def stop_tasks(self) -> None:
        if self.economy_snapshot_task.is_running():
            self.economy_snapshot_task.cancel()
        if self.member_snapshot_task.is_running():
            self.member_snapshot_task.cancel()
        if self.performance_snapshot_task.is_running():
            self.performance_snapshot_task.cancel()
