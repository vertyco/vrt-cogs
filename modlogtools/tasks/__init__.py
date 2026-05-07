from ..abc import CompositeMetaClass
from .expiry import ExpiryTask


class TaskLoops(ExpiryTask, metaclass=CompositeMetaClass):
    """Subclass all task loops."""
