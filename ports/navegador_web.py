from abc import ABC, abstractmethod

from core.entities import Publicacao, Analise


class NavegadorWeb(ABC):
    @abstractmethod
    def login(self) -> None: ...

    @abstractmethod
    def navegar_para_publicacoes(self) -> None: ...

    @abstractmethod
    def aplicar_filtros(self) -> None: ...

    @abstractmethod
    def raspar_proxima_publicacao(self) -> Publicacao | None: ...

    @abstractmethod
    def marcar_sem_providencia(self) -> bool: ...

    @abstractmethod
    def abrir_e_criar_compromisso(
        self, publicacao: Publicacao, analise: Analise
    ) -> bool: ...
