"""Abstract base classes for connectors."""

import json
from abc import ABC, abstractmethod


class Connector(ABC):
    def __init__(self) -> None:
        self._paused = False

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Fetch items. Each item must have an 'id' field."""
        ...

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused


class TokenConnector(Connector):
    """Base for connectors that authenticate via a token file. Starts paused if no token."""

    def __init__(self, token_path: str) -> None:
        super().__init__()
        self.token_path = token_path
        if not token_path:
            self.pause()

    def _access_token(self) -> str:
        with open(self.token_path) as f:
            return json.load(f)["access_token"]
