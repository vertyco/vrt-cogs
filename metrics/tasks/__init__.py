# Task loops can be defined here
from ..abc import CompositeMetaClass
from .snapshot import Snapshot


class TaskLoops(Snapshot, metaclass=CompositeMetaClass):
    """
    Subclass all task loops in this directory so you can import this single task loop class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """

    def start_tasks(self) -> None:
        if not self.take_snapshot.is_running():
            self.take_snapshot.start()

    def stop_tasks(self) -> None:
        if self.take_snapshot.is_running():
            self.take_snapshot.cancel()
