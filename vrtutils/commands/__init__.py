from ..abc import CompositeMetaClass
from .bot import BotInfo
from .botemojis import EmojiManager
from .chatexport import ChatExport
from .dcord import Dcord
from .disk import DiskBench
from .guildprofiles import GuildProfiles
from .logs import Logs
from .misc import Misc
from .todo import ToDo
from .updates import Updates
from .zipper import Zipper


class Utils(
    BotInfo,
    EmojiManager,
    ChatExport,
    Dcord,
    DiskBench,
    GuildProfiles,
    Logs,
    Misc,
    ToDo,
    Updates,
    Zipper,
    metaclass=CompositeMetaClass,
):
    """Subclass all commands"""
