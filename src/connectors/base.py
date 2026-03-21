"""Abstract base classes for connectors."""

import json
import os
from abc import ABC, abstractmethod


class Connector(ABC):
    def __init__(self) -> None:
        self._paused = False
        self.error: str | None = None

    @abstractmethod
    def fetch(self, since: float | None = None) -> list[dict]:
        """Fetch items new/updated since Unix timestamp `since`, or recent if None. Each item must have an 'id' field."""
        ...

    def pause(self, error: str | None = None) -> None:
        self._paused = True
        if error is not None:
            self.error = error

    def resume(self) -> None:
        self._paused = False
        self.error = None

    @property
    def paused(self) -> bool:
        return self._paused


class TokenConnector(Connector):
    """Base for connectors that authenticate via a token file. Starts paused if no token."""

    def __init__(self, token_path: str) -> None:
        super().__init__()
        self.token_path = token_path
        if not token_path or not os.path.exists(token_path):
            self.pause()

    def _access_token(self) -> str:
        with open(self.token_path) as f:
            return json.load(f)["access_token"]
