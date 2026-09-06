\
from __future__ import annotations
from abc import ABC, abstractmethod
from job_agent.schemas import RawJob

class JobProvider(ABC):
    @abstractmethod
    def search(self, *, role: str, location: str, results_per_page: int = 25) -> list[RawJob]:
        raise NotImplementedError
