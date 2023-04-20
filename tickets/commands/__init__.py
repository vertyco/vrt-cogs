from ..abc import CompositeMetaClass
from .admin import AdminCommands
from .base import BaseCommands


class TicketCommands(
    AdminCommands, BaseCommands, metaclass=CompositeMetaClass
):
    """Subclass all command classes"""
