from ..abc import CompositeMetaClass
from .levelups import LevelUps
from .profile import ProfileFormatting
from .weeklyreset import WeeklyReset
from .checks import Checks


class SharedFunctions(LevelUps, ProfileFormatting, WeeklyReset, Checks, metaclass=CompositeMetaClass):
    """
    Subclass all shared metaclassed parts of the cog

    This includes classes with functions available to other cogs
    """
