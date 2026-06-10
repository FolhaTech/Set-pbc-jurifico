#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config/di.py
------------
Injeção de dependências — monta todos os objetos e retorna os casos de uso prontos.
"""

import sys
import uuid
import logging
import os
import subprocess
import json
import time

from core.services.calcular_prazo import CalcularPrazo
from core.services.classificador_polo import ClassificadorPolo
from core.use_cases.analisar_publicacao import AnalisarPublicacao
from core.use_cases.processar_lista import ProcessarLista
from ports.navegador_web import NavegadorWeb
from ports.cliente_ia import ClienteIA
from ports.repositorio import Repositorio
from adapters.persistencia.json_repositorio import JsonRepositorio
from adapters.ia.adapta_one_cliente import AdaptaOneCliente
from adapters.web.selenium_navegador import SeleniumNavegador

from config.settings import ARQUIVO_JSON

logger = logging.getLogger(__name__)


# ─── Token Adapta ONE ──────────────────────────────────────────────────────


def obter_token_adapta() -> str:
    """Extrai o token JWT do Adapta ONE via script Node.js."""
    try:
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "extract_token.js",
        )
        if not os.path.exists(script_path):
            script_path = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
                "Automação publicação Juridico",
                "extract_token.js",
            )
        if os.path.exists(script_path):
            result = subprocess.run(
                ["node", script_path], capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            if data.get("success") and data.get("token"):
                return data["token"]
    except Exception as e:
        logger.warning(f"[DI] Falha ao extrair token via Node: {e}")
    return ""


def verificar_token_expirado(token: str) -> bool:
    """Verifica se o token JWT está expirado (< 60s)."""
    import base64

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return True
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        return payload.get("exp", 0) < time.time() + 60
    except Exception:
        return True


def renovar_token() -> str:
    """Tenta renovar o token abrindo o Adapta ONE Desktop."""
    exe_path = r"C:\Program Files\adapta-one-agent-desktop\adapta-one-agent-desktop.exe"
    if not os.path.exists(exe_path):
        logger.warning("[DI] Executável do Adapta ONE não encontrado.")
        return ""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7
        subprocess.Popen([exe_path], startupinfo=si)
        start = time.time()
        while time.time() - start < 12:
            time.sleep(1)
            token = obter_token_adapta()
            if token and not verificar_token_expirado(token):
                logger.info("[DI] ✅ Token renovado com sucesso.")
                return token
    except Exception as e:
        logger.error(f"[DI] Erro ao renovar token: {e}")
    return ""


# ─── Verificador de cliente (planilha) ──────────────────────────────────────


def verificar_cliente_planilha(polo_a: str, numero_processo: str = None) -> dict:
    """
    Verifica se polo_a é nosso cliente na planilha Excel.
    Retorna: {'e_nosso': bool, 'cliente_planilha': str|None, 'contrario': str|None}
    """
    try:
        import openpyxl
    except ImportError:
        openpyxl = None

    from config.settings import PLANILHA_BASE

    if not openpyxl:
        return {"e_nosso": True, "cliente_planilha": None, "contrario": None}

    if not os.path.exists(PLANILHA_BASE):
        logger.warning(f"[DI] Planilha não encontrada: {PLANILHA_BASE}")
        return {"e_nosso": True, "cliente_planilha": None, "contrario": None}

    import unicodedata

    def _normalizar(texto: str) -> str:
        if not texto:
            return ""
        nfkd = unicodedata.normalize("NFKD", texto.strip().lower())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    try:
        wb = openpyxl.load_workbook(PLANILHA_BASE, read_only=True, data_only=True)
        ws = wb.active
        polo_a_norm = _normalizar(polo_a)
        proc_norm = (numero_processo or "").replace("-", "").replace(".", "").strip()

        for row in ws.iter_rows(min_row=2, values_only=True):
            num_proc_cel = str(row[2] or "").replace("-", "").replace(".", "").strip()
            cliente_cel = str(row[3] or "")
            contrario_cel = str(row[9] or "")
            cliente_norm = _normalizar(cliente_cel)

            if proc_norm and num_proc_cel == proc_norm:
                e_nosso = polo_a_norm in cliente_norm or cliente_norm in polo_a_norm
                return {
                    "e_nosso": e_nosso,
                    "cliente_planilha": cliente_cel,
                    "contrario": contrario_cel,
                }

            if (
                cliente_norm
                and polo_a_norm
                and (polo_a_norm in cliente_norm or cliente_norm in polo_a_norm)
            ):
                return {
                    "e_nosso": True,
                    "cliente_planilha": cliente_cel,
                    "contrario": contrario_cel,
                }

        wb.close()
        return {"e_nosso": False, "cliente_planilha": None, "contrario": None}
    except Exception as e:
        logger.error(f"[DI] Erro ao ler planilha: {e}")
        return {"e_nosso": True, "cliente_planilha": None, "contrario": None}


# ─── Container de dependências ─────────────────────────────────────────────


class Container:
    """Monta e gerencia todas as dependências da aplicação."""

    def __init__(self, usar_ia: bool = True):
        self._usar_ia = usar_ia
        self._navegador: SeleniumNavegador | None = None
        self._repositorio: JsonRepositorio | None = None
        self._cliente_ia: AdaptaOneCliente | None = None
        self._calculador: CalcularPrazo | None = None
        self._classificador: ClassificadorPolo | None = None

    @property
    def navegador(self) -> SeleniumNavegador:
        if self._navegador is None:
            self._navegador = SeleniumNavegador(
                usar_undetected=True,
                cliente_ia=self._cliente_ia,
            )
        return self._navegador

    @property
    def repositorio(self) -> JsonRepositorio:
        if self._repositorio is None:
            self._repositorio = JsonRepositorio()
        return self._repositorio

    @property
    def cliente_ia(self) -> AdaptaOneCliente | None:
        if self._cliente_ia is None and self._usar_ia:
            token = obter_token_adapta()
            if not token or verificar_token_expirado(token):
                token = renovar_token() or token
            if not token:
                logger.error("[DI] ❌ Token do Adapta ONE não obtido.")
                return None
            self._cliente_ia = AdaptaOneCliente(token)
            logger.info("[DI] ✅ Cliente Adapta ONE conectado.")
        return self._cliente_ia

    @property
    def calculador(self) -> CalcularPrazo:
        if self._calculador is None:
            self._calculador = CalcularPrazo()
        return self._calculador

    @property
    def classificador(self) -> ClassificadorPolo:
        if self._classificador is None:
            self._classificador = ClassificadorPolo()
        return self._classificador

    def criar_analisar_publicacao(self) -> AnalisarPublicacao:
        return AnalisarPublicacao(
            repositorio=self.repositorio,
            navegador=self.navegador,
            calculador_prazo=self.calculador,
            classificador=self.classificador,
            cliente_ia=self.cliente_ia,
        )

    def criar_processar_lista(self, max_publicacoes: int = 50) -> ProcessarLista:
        return ProcessarLista(
            navegador=self.navegador,
            repositorio=self.repositorio,
            cliente_ia=self.cliente_ia,
            max_publicacoes=max_publicacoes,
        )

    def fechar(self) -> None:
        if self._navegador:
            self._navegador.fechar()
            self._navegador = None
