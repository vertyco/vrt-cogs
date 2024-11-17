from ..abc import CompositeMetaClass
from .guild import GuildListener
from .members import MemberListener
from .messages import MessageListener
from .reactions import ReactionListener
from .voice import VoiceListener


class Listeners(
    GuildListener,
    MemberListener,
    MessageListener,
    ReactionListener,
    VoiceListener,
    metaclass=CompositeMetaClass,
):
    """Subclass all listener classes"""
