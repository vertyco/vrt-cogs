from ..abc import CompositeMetaClass
from .admin import Admin
from .owner import Owner


class Commands(Admin, Owner, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
