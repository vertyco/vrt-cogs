from ..abc import CompositeMetaClass
from .admin import Admin


class Commands(Admin, metaclass=CompositeMetaClass):
    """Subclass all command classes"""
