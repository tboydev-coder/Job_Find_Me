from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str | None = None
    

class SearchProvider(ABC):

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
        time_range: str | None = None,
    ) -> list[SearchResult]:
        raise NotImplementedError
