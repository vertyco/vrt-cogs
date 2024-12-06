from ..abc import CompositeMetaClass
from .messages import MessageListener


class Listeners(MessageListener, metaclass=CompositeMetaClass):
    """
    Subclass all listeners in this directory so you can import this single Listeners class in your cog's class constructor.

    See `commands` directory for the same pattern.
    """
