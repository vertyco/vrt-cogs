from ..abc import CompositeMetaClass
from .members import MemberListener
from .messages import MessageListener
from .voice import VoiceListener


class Listeners(
    MemberListener,
    MessageListener,
    VoiceListener,
    metaclass=CompositeMetaClass,
):
    """Subclass all listener classes"""
