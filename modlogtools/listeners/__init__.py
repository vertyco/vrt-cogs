from ..abc import CompositeMetaClass
from .cases import CaseListeners


class Listeners(CaseListeners, metaclass=CompositeMetaClass):
    """Subclass all listeners."""
