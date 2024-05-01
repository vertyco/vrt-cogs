from ..abc import CompositeMetaClass
from .admin import Admin
from .adminbase import AdminBase
from .user import User


class Commands(Admin, AdminBase, User, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
