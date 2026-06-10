import time
import logging
from datetime import datetime
from typing import Optional

from core.entities import (
    Publicacao, Analise, ConteudoParsed, FlagsPublicacao, Advogado,
)
from ports.navegador_web import NavegadorWeb
from ports.cliente_ia import ClienteIA
from adapters.web.driver_setup import configurar_driver
from adapters.web.login import login_thomson_reuters
from adapters.web.navegacao import (
    acessar_publicacoes,
    selecionar_periodo_60_dias,
    abrir_mais_filtros,
    selecionar_responsavel,
    aplicar_filtros,
)
from adapters.web.scraper import raspar_detalhes_publicacao
from adapters.web.acoes import marcar_sem_providencia, clicar_link_processo
from adapters.infra.logging_utils import diagnosticar_pagina
from config.settings import RESPONSAVEL_ALVO

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


logger = logging.getLogger(__name__)


class SeleniumNavegador(NavegadorWeb):
    """Implementacao de NavegadorWeb usando Selenium + modulos existentes."""

    def __init__(self, usar_undetected: bool = True, cliente_ia: ClienteIA | None = None):
        self._driver = None
        self._usar_undetected = usar_undetected
        self._cliente_ia = cliente_ia

    @property
    def driver(self):
        if self._driver is None:
            self._driver = configurar_driver(usar_undetected=self._usar_undetected)
        return self._driver

    def login(self) -> None:
        login_thomson_reuters(self.driver)
        logger.info("[NAV] Aguardando SPA estabilizar...")
        time.sleep(10)
        diagnosticar_pagina(self.driver, "pos_login")

    def navegar_para_publicacoes(self) -> None:
        acessar_publicacoes(self.driver)
        time.sleep(3)
        diagnosticar_pagina(self.driver, "pos_publicacoes")

    def aplicar_filtros(self) -> None:
        selecionar_periodo_60_dias(self.driver)
        time.sleep(2)
        abrir_mais_filtros(self.driver)
        time.sleep(3)
        selecionar_responsavel(self.driver, RESPONSAVEL_ALVO)
        time.sleep(1)
        aplicar_filtros(self.driver)
        time.sleep(3)

    def raspar_proxima_publicacao(self) -> Optional[Publicacao]:
        try:
            items = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "div[id^='publication-item-']")
                )
            )
            if not items:
                logger.warning("[NAV] Nenhuma publicação encontrada.")
                return None

            primeiro = items[0]
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", primeiro
            )
            primeiro.click()
            time.sleep(3)

            dados_dict = raspar_detalhes_publicacao(self.driver)
            return self._dict_para_publicacao(dados_dict)

        except Exception as e:
            logger.error(f"[NAV] Erro ao raspar publicação: {e}")
            return None

    def marcar_sem_providencia(self) -> bool:
        return marcar_sem_providencia(self.driver)

    def abrir_e_criar_compromisso(
        self, publicacao: Publicacao, analise: Analise
    ) -> bool:
        dados_dict = self._publicacao_para_dict(publicacao)
        adapta_info = None
        if self._cliente_ia is not None:
            from adapters.ia.adapta_one_cliente import AdaptaOneCliente
            if isinstance(self._cliente_ia, AdaptaOneCliente):
                adapta_info = {
                    "client": self._cliente_ia,
                    "expert_id": self._cliente_ia._expert_id or "",
                    "chat_id": self._cliente_ia._chat_id or "",
                }
        return clicar_link_processo(self.driver, dados_dict, adapta_info=adapta_info)

    def fechar(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    # ── Conversão dict → Publicacao ──────────────────────────────

    def _dict_para_publicacao(self, d: dict) -> Publicacao:
        """Converte o dict do scraper para entidade Publicacao."""
        flags = FlagsPublicacao(
            eh_sigiloso=d.get("conteudo_parsed", {}).get("flags", {}).get("eh_sigiloso", False),
            processo_sigiloso=d.get("conteudo_parsed", {}).get("flags", {}).get("processo_sigiloso", False),
            consulta_autos_digitais=d.get("conteudo_parsed", {}).get("flags", {}).get("consulta_autos_digitais", False),
        )
        advogados = [
            Advogado(nome=a.get("nome", ""), oab=a.get("oab", ""))
            for a in d.get("conteudo_parsed", {}).get("advogados", [])
        ]
        conteudo_parsed = ConteudoParsed(
            campos=d.get("conteudo_parsed", {}).get("campos", {}),
            advogados=advogados,
            flags=flags,
            texto_bruto=d.get("conteudo_parsed", {}).get("texto_bruto", ""),
        )
        data_disp = d.get("data_disponibilizacao")
        if data_disp and data_disp != "N/A":
            try:
                data_disp_parsed = datetime.strptime(data_disp, "%d/%m/%Y").date()
            except (ValueError, TypeError):
                data_disp_parsed = None
        else:
            data_disp_parsed = None

        return Publicacao(
            url_pagina=d.get("url_pagina", ""),
            data_raspagem=datetime.fromisoformat(d["data_raspagem"]) if d.get("data_raspagem") else datetime.now(),
            processo_numero=d.get("processo_numero", "N/A"),
            processo_href=d.get("processo_href"),
            tipo=d.get("tipo", "N/A"),
            badge=d.get("badge", "N/A"),
            data_disponibilizacao=data_disp_parsed,
            fonte_tribunal=d.get("fonte_tribunal", "N/A"),
            fonte_diario=d.get("fonte_diario", "N/A"),
            conteudo=d.get("conteudo", ""),
            conteudo_parsed=conteudo_parsed,
        )

    # ── Conversão Publicacao → dict (compatibilidade módulos antigos) ──

    def _publicacao_para_dict(self, pub: Publicacao) -> dict:
        """Converte Publicacao de volta para dict (compatibilidade com módulos antigos)."""
        return {
            "url_pagina": pub.url_pagina,
            "data_raspagem": pub.data_raspagem.isoformat() if pub.data_raspagem else "",
            "processo_numero": pub.processo_numero,
            "processo_href": pub.processo_href,
            "tipo": pub.tipo,
            "badge": pub.badge,
            "data_disponibilizacao": pub.data_disponibilizacao.strftime("%d/%m/%Y") if pub.data_disponibilizacao else "N/A",
            "fonte_tribunal": pub.fonte_tribunal,
            "fonte_diario": pub.fonte_diario,
            "conteudo": pub.conteudo,
            "conteudo_parsed": {
                "campos": pub.conteudo_parsed.campos,
                "advogados": [{"nome": a.nome, "oab": a.oab} for a in pub.conteudo_parsed.advogados],
                "flags": {
                    "eh_sigiloso": pub.conteudo_parsed.flags.eh_sigiloso,
                    "processo_sigiloso": pub.conteudo_parsed.flags.processo_sigiloso,
                    "consulta_autos_digitais": pub.conteudo_parsed.flags.consulta_autos_digitais,
                },
                "texto_bruto": pub.conteudo_parsed.texto_bruto,
            },
            "advogados": [{"nome": a.nome, "oab": a.oab} for a in pub.conteudo_parsed.advogados],
        }