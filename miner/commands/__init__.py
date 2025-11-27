from ..abc import CompositeMetaClass
from .admin import Admin
from .database import DatabaseCommands
from .user import User


class Commands(Admin, DatabaseCommands, User, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
