from ..abc import CompositeMetaClass
from .admin import Admin
from .user import User


class Commands(Admin, User, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
