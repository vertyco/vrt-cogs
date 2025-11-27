# Task loops can be defined here
from ..abc import CompositeMetaClass


class TaskLoops(metaclass=CompositeMetaClass):
    """
    Subclass all task loops in this directory so you can import this single task loop class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """
