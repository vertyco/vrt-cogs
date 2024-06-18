from ..abc import CompositeMetaClass
from .admin import Admin
from .data import DataAdmin
from .owner import Owner
from .stars import Stars
from .user import User
from .weekly import Weekly


class Commands(
    Admin,
    DataAdmin,
    Owner,
    Stars,
    User,
    Weekly,
    metaclass=CompositeMetaClass,
):
    """Subclass all command classes"""
