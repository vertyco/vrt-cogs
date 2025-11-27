from ..abc import CompositeMetaClass
from .member import MemberListener
from .messages import MessageListener


class Listeners(MemberListener, MessageListener, metaclass=CompositeMetaClass):
    pass
