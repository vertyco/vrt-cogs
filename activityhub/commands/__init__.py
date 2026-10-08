from ..abc import CompositeMetaClass
from .owner import OwnerCommands
from .user import UserCommands


class Commands(
    UserCommands,
    OwnerCommands,
    metaclass=CompositeMetaClass,
):
    """Subclass all command mixins"""
