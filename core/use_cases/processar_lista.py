import logging
import pathlib
import time
from typing import Optional, Callable

from selenium.webdriver.common.by import By

from core.enums import StatusAcao
from core.services.calcular_prazo import CalcularPrazo
from core.services.classificador_polo import ClassificadorPolo
from core.use_cases.analisar_publicacao import AnalisarPublicacao
from ports.cliente_ia import ClienteIA
from ports.navegador_web import NavegadorWeb
from ports.repositorio import Repositorio

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "scripts"


def _js(nome_arquivo: str) -> str:
    return (_SCRIPTS_DIR / nome_arquivo).read_text(encoding="utf-8")


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
                polo_a=polo_a,
                numero_processo=pub.processo_numero,
                conteudo_publicacao=pub.conteudo or "",
            )
            return resultado.get("e_nosso", True)
        return True

    def _ja_foi_processado(self, pub) -> bool:
        existente = self._repo.buscar_por_processo(pub.processo_numero)
        if existente is None:
            return False

        if existente.analise is None:
            return False

        if existente.analise.agendamento is not None:
            logging.info(
                f"[PULAR] Processo {pub.processo_numero} já analisado e agendado "
                f"em {existente.analise.agendamento.data_agendamento}. "
                f"Status: {existente.analise.status_acao.value}"
            )
            return True

        if existente.analise.status_acao in (
            StatusAcao.SEM_PROVIDENCIA,
            StatusAcao.TRATADO,
        ):
            logging.info(
                f"[PULAR] Processo {pub.processo_numero} já finalizado como "
                f"'{existente.analise.status_acao.value}'"
            )
            return True
        return False

    def executar_primeira(self) -> int:
        self._garantir_aba_pendentes()
        while True:
            pub = self._nav.raspar_proxima_publicacao()
            if not pub:
                return 0
            if self._ja_foi_processado(pub):
                self._pular_e_avancar()
                continue
            e_nosso = self._verificar_e_nosso(pub)
            self._analisar.executar(pub, e_nosso=e_nosso)
            self._repo.salvar(pub)
            self._imprimir_resumo(pub)
            self._nav.reiniciar_indice()
            return 1

    def _pular_e_avancar(self) -> None:
        self._nav.fechar_painel_detalhes()

    def executar_todas(self) -> int:
        processadas = 0
        while processadas < self._max:
            self._garantir_aba_pendentes()
            pub = self._nav.raspar_proxima_publicacao()
            if not pub:
                break
            if self._ja_foi_processado(pub):
                self._pular_e_avancar()
                continue
            e_nosso = self._verificar_e_nosso(pub)
            self._analisar.executar(pub, e_nosso=e_nosso)
            self._repo.salvar(pub)
            self._imprimir_resumo(pub)
            self._nav.reiniciar_indice()
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

    def _garantir_aba_pendentes(self) -> None:
        try:
            driver = self._nav.driver
            if driver is None:
                logging.warning(
                    "[NAV] Driver nao inicializado — pulando garantia de aba."
                )
                return

            # ── 1) Detectar se ja esta em 'Pendentes' ──
            try:
                driver.execute_script(_js("check-pendings.js"))
                ja_ativa = driver.execute_script(
                    "return window.__abaPendentesJaAtiva();"
                )

                if ja_ativa:
                    logging.debug("[NAV] Aba 'Pendentes' ja esta ativa.")
                    return
            except Exception:
                pass

            # ── 2) Tentar clicar em 'Pendentes' ──
            xpath_pendentes = [
                "//a[normalize-space(.)='Pendentes']",
                "//button[normalize-space(.)='Pendentes']",
                "//li[contains(@class,'active')]//a[contains(.,'Pendente')]",
                "//a[contains(@href, 'status=Pendente') or contains(@href, 'status=Pendentes')]",
                "//span[normalize-space(.)='Pendentes']/parent::a",
                "//span[normalize-space(.)='Pendentes']/parent::button",
            ]
            clicou = False
            for xp in xpath_pendentes:
                try:
                    el = driver.find_element(By.XPATH, xp)
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(2)
                        logging.info(
                            "[NAV] Aba 'Pendentes' reativada para proxima publicacao."
                        )
                        clicou = True
                        break
                except Exception:
                    continue

            if not clicou:
                logging.warning("[NAV] Nao foi possivel reativar a aba 'Pendentes'.")
                return

            # ── 3) Resetar indice apos trocar de aba ──
            try:
                self._nav.reiniciar_indice()
            except Exception as e:
                logging.warning(f"[NAV] Falha ao reiniciar indice: {e}")

            # ── 4) BLINDAGEM: verificar se filtros foram preservados ──
            try:
                from config.settings import RESPONSAVEL_ALVO

                driver.execute_script(_js("filter-check.js"))
                resp_ok = driver.execute_script(
                    "return window.__filtroResponsavelPreservado();"
                )

                if not resp_ok:
                    logging.warning(
                        "[NAV] Filtros resetaram ao trocar aba. Reaplicando..."
                    )
                    self._nav.aplicar_filtros(responsavel=RESPONSAVEL_ALVO)
            except Exception as e:
                logging.warning(f"[NAV] Falha ao verificar filtros: {e}")

        except Exception as e:
            logging.error(f"[NAV] Falha ao tentar reativar aba 'Pendentes': {e}")
