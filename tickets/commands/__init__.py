from ..abc import CompositeMetaClass
from .admin import AdminCommands
from .analytics import AnalyticsCommands
from .base import BaseCommands


class TicketCommands(AdminCommands, AnalyticsCommands, BaseCommands, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
