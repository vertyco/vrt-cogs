from ..abc import CompositeMetaClass
from .admin import AdminCommands
from .user import UserCommands


class Commands(
    UserCommands,
    AdminCommands,
    metaclass=CompositeMetaClass,
):
    """Subclass all command mixins"""
