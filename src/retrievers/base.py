from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional


class BaseRetriever(ABC):
    """Abstract retriever interface."""

    @abstractmethod
    def add(
        self,
        text: str,
        *,
        event_ts: int,
        visible_after_ts: Optional[int] = None,
        namespace: str = "train",
        metadata: Optional[dict] = None,
    ) -> None:
        ...

    @abstractmethod
    def query(
        self,
        text: str,
        *,
        k: int,
        cutoff_ts: int,
        namespaces: Optional[Iterable[str]] = None,
        time_decay_lambda: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Return up to k results as dicts with keys: text, meta, score, event_ts."""
        ...

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def save_checkpoint(self, checkpoint_path: str) -> None:
        ...

    @abstractmethod
    def load_checkpoint(self, checkpoint_path: str) -> None:
        ...
