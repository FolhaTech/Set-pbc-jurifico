from abc import ABC, abstractmethod
from typing import List

from core.entities import Publicacao


class Repositorio(ABC):
    @abstractmethod
    def salvar(self, publicacao: Publicacao) -> None:
        ...

    @abstractmethod
    def listar_todas(self) -> List[Publicacao]:
        ...

    @abstractmethod
    def buscar_por_processo(self, numero: str) -> Publicacao | None:
        ...

    @abstractmethod
    def gerar_relatorio(self) -> dict:
        ...
