"""
Kontrak interface untuk modul AI.
"""

from abc import ABC, abstractmethod


class KBLIClassifier(ABC):
    """Kontrak classifier KBLI agar implementasi dapat dipertukarkan."""

    @abstractmethod
    def classify(self, content: str | None, title: str | None = None) -> str | None:
        """Kembalikan kode KBLI atau None jika tidak terklasifikasi."""
        raise NotImplementedError
