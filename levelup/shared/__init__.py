from ..abc import CompositeMetaClass
from .levelups import LevelUps
from .profile import ProfileFormatting
from .weeklyreset import WeeklyReset


class SharedFunctions(LevelUps, ProfileFormatting, WeeklyReset, metaclass=CompositeMetaClass):
    """
    Subclass all shared classes

    This includes classes with functions available to other cogs
    """
