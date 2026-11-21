"""Port to read the central configuration (#302)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping


class ICentralConfigReader(ABC):
    """Reads the values shared by every device."""

    @abstractmethod
    def read_central_values(self) -> Mapping[str, object | None]:
        """Return the stored central values.

        Returns:
            The shareable values that have a central value; an empty mapping when there is no
            central configuration, so that devices fall back to their built-in defaults.
        """
