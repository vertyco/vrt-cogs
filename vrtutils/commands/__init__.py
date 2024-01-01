from ..abc import CompositeMetaClass
from .bot import BotInfo
from .chatexport import ChatExport
from .dcord import Dcord
from .disk import DiskBench
from .misc import Misc
from .zipper import Zipper


class Utils(
    BotInfo,
    ChatExport,
    Dcord,
    DiskBench,
    Misc,
    Zipper,
    metaclass=CompositeMetaClass,
):
    """Subclass all commands"""
