"""Errors that services can raise without depending on FastAPI."""


class ServiceError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
