from ..abc import CompositeMetaClass
from .events import Events


class Listeners(Events, metaclass=CompositeMetaClass):
    """Subclass all listeners"""
