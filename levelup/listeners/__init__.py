from ..abc import CompositeMetaClass
from .guild import GuildListener
from .members import MemberListener
from .messages import MessageListener
from .voice import VoiceListener


class Listeners(
    GuildListener,
    MemberListener,
    MessageListener,
    VoiceListener,
    metaclass=CompositeMetaClass,
):
    """Subclass all listener classes"""
