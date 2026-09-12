from ..abc import CompositeMetaClass
from .admin import Admin
from .base import Base
from .jobs import Jobs


class AssistantCommands(Admin, Base, Jobs, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
