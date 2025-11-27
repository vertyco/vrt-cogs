class BaseORMError(Exception):
    """Base class for all ORM-related errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ConnectionTimeoutError(BaseORMError):
    pass


class UNCPathError(BaseORMError):
    pass


class DirectoryError(BaseORMError):
    pass
