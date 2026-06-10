from datetime import date
from typing import Optional

from core.entities import Publicacao, Analise
from core.enums import LadoProcesso, Urgencia, StatusAcao
from core.services.calcular_prazo import CalcularPrazo
from core.services.classificador_polo import ClassificadorPolo
from ports.repositorio import Repositorio
from ports.cliente_ia import ClienteIA
from ports.navegador_web import NavegadorWeb


class AnalisarPublicacao:
    def __init__(
        self,
        repositorio: Repositorio,
        navegador: NavegadorWeb,
        calculador_prazo: CalcularPrazo,
        classificador: ClassificadorPolo,
        cliente_ia: Optional[ClienteIA] = None,
    ):
        self._repo = repositorio
        self._nav = navegador
        self._calc = calculador_prazo
        self._classificador = classificador
        self._ia = cliente_ia

    def executar(self, publicacao: Publicacao, e_nosso: bool) -> Publicacao:
        lado = self._classificador.classificar(e_nosso)
        analise = self._obter_analise(publicacao, lado)
        prazo_dias = analise.prazo_dias or 15
        data_disp = publicacao.data_disponibilizacao or date.today()
        analise.agendamento = self._calc.calcular_prazo(prazo_dias, data_disp)
        publicacao.analise = analise
        self._executar_acao(publicacao)
        self._repo.salvar(publicacao)
        return publicacao

    def _obter_analise(
        self, pub: Publicacao, lado: LadoProcesso
    ) -> Analise:
        if self._ia:
            return self._ia.analisar(pub, lado)
        return self._analise_offline(pub, lado)

    def _analise_offline(
        self, pub: Publicacao, lado: LadoProcesso
    ) -> Analise:
        return Analise(
            lado=lado,
            resumo="Análise offline baseada na planilha.",
            urgencia=Urgencia.MEDIA,
            prazo_dias=15,
            acao_recomendada=(
                "Revisar análise processual."
                if lado == LadoProcesso.NOSSO_CLIENTE
                else "Sem providências necessárias."
            ),
            requer_acao=(lado == LadoProcesso.NOSSO_CLIENTE),
            fonte_ia="offline",
        )

    def _executar_acao(self, pub: Publicacao) -> None:
        if not pub.analise:
            return
        if pub.analise.lado == LadoProcesso.OPERADORA:
            sucesso = self._nav.marcar_sem_providencia()
            pub.analise.status_acao = (
                StatusAcao.SEM_PROVIDENCIA if sucesso else StatusAcao.FALHA
            )
        else:
            self._nav.abrir_e_criar_compromisso(pub, pub.analise)
            pub.analise.status_acao = StatusAcao.PENDENTE