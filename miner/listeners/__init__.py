from ..abc import CompositeMetaClass
from .messages import MessageListener


class Listeners(MessageListener, metaclass=CompositeMetaClass):
    pass
