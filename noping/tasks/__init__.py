from ..abc import CompositeMetaClass
from .schedule_sync import ScheduleSync


class TaskLoops(ScheduleSync, metaclass=CompositeMetaClass):
    """Subclass all task loops"""
