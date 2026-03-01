from abc import ABC, abstractmethod
from typing import Any, Dict


class CollectorBase(ABC):
    """
    Base class for all data collectors.
    Collectors are responsible for fetching raw data from a source.
    """

    @abstractmethod
    async def collect(self, input_value: str) -> Dict[str, Any]:
        """
        Main entry point to fetch data.
        Returns a dictionary with source and raw_data.
        """
        pass
