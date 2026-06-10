from abc import ABC, abstractmethod

from core.entities import Publicacao, Analise
from core.enums import LadoProcesso


class ClienteIA(ABC):
    @abstractmethod
    def analisar(self, publicacao: Publicacao, lado: LadoProcesso) -> Analise: ...
