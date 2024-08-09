from ..abc import CompositeMetaClass
from .bot import BotInfo
from .botemojis import EmojiManager
from .chatexport import ChatExport
from .dcord import Dcord
from .disk import DiskBench
from .logs import Logs
from .misc import Misc
from .todo import ToDo
from .zipper import Zipper


class Utils(
    BotInfo,
    EmojiManager,
    ChatExport,
    Dcord,
    DiskBench,
    Logs,
    Misc,
    ToDo,
    Zipper,
    metaclass=CompositeMetaClass,
):
    """Subclass all commands"""
