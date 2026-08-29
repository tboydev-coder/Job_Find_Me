from abc import ABC, abstractmethod

from .schemas import JobData


class JobSource(ABC):

    @abstractmethod
    async def search_jobs(
        self,
        query: str,
    ) -> list[JobData]:
        pass