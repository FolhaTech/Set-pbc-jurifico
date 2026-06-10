import logging
from typing import Optional, Callable

from ports.navegador_web import NavegadorWeb
from ports.cliente_ia import ClienteIA
from ports.repositorio import Repositorio
from core.use_cases.analisar_publicacao import AnalisarPublicacao
from core.services.calcular_prazo import CalcularPrazo
from core.services.classificador_polo import ClassificadorPolo

logger = logging.getLogger(__name__)


class ProcessarLista:
    def __init__(
        self,
        navegador: NavegadorWeb,
        repositorio: Repositorio,
        cliente_ia: Optional[ClienteIA] = None,
        max_publicacoes: int = 50,
        verificacao_planilha: Optional[Callable] = None,
    ):
        calculador = CalcularPrazo()
        classificador = ClassificadorPolo()
        self._analisar = AnalisarPublicacao(
            repositorio=repositorio,
            navegador=navegador,
            calculador_prazo=calculador,
            classificador=classificador,
            cliente_ia=cliente_ia,
        )
        self._repo = repositorio
        self._nav = navegador
        self._max = max_publicacoes
        self._verificacao_planilha = verificacao_planilha

    def _verificar_e_nosso(self, pub) -> bool:
        if self._verificacao_planilha:
            polo_a = pub.conteudo_parsed.campos.get("polo_a", "")
            resultado = self._verificacao_planilha(
                polo_a=polo_a, numero_processo=pub.processo_numero
            )
            return resultado.get("e_nosso", True)
        return True

    def executar_primeira(self) -> int:
        pub = self._nav.raspar_proxima_publicacao()
        if not pub:
            return 0
        e_nosso = self._verificar_e_nosso(pub)
        self._analisar.executar(pub, e_nosso=e_nosso)
        self._repo.salvar(pub)
        self._imprimir_resumo(pub)
        return 1

    def executar_todas(self) -> int:
        processadas = 0
        while processadas < self._max:
            pub = self._nav.raspar_proxima_publicacao()
            if not pub:
                break
            e_nosso = self._verificar_e_nosso(pub)
            self._analisar.executar(pub, e_nosso=e_nosso)
            self._repo.salvar(pub)
            self._imprimir_resumo(pub)
            processadas += 1
        return processadas

    def _imprimir_resumo(self, pub) -> None:
        if not pub.analise:
            return
        decisao = "AGENDAR" if pub.analise.requer_acao else "SEM PROVIDENCIA"
        data_str = ""
        if pub.analise.agendamento:
            data_str = pub.analise.agendamento.data_agendamento.strftime("%d/%m/%Y")
        print(f"\n{'*' * 50}")
        print(f"  Processo: {pub.processo_numero}")
        print(f"  Decisao: {decisao}  |  Agendamento: {data_str or 'N/A'}")
        print(f"{'*' * 50}\n")
