from ..common.abc import CompositeMetaClass
from .base import Base


class BaseCommands(Base, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
