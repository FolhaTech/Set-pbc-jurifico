from abc import ABC, abstractmethod

from selenium.webdriver.remote.webdriver import WebDriver

from core.entities import Publicacao, Analise


class NavegadorWeb(ABC):
    @property
    @abstractmethod
    def driver(self) -> WebDriver: ...

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

    @abstractmethod
    def fechar_painel_detalhes(self) -> None: ...

    @abstractmethod
    def reiniciar_indice(self) -> None: ...

    @abstractmethod
    def decrementar_indice(self) -> None: ...
