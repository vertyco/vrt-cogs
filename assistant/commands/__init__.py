from ..abc import CompositeMetaClass
from .admin import Admin
from .base import Base


class AssistantCommands(Admin, Base, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
