#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/utils.py
----------------
Funções utilitárias compartilhadas por todos os módulos:
  - Logging
  - Screenshots
  - Diagnóstico de página
  - Persistência em JSON
  - Cálculo de datas de agendamento
  - Extração de retry delay
"""

import os
import re
import json
import hashlib
import logging
import unicodedata
from datetime import datetime, timedelta
from config.settings import (
    PASTA_SCREENSHOTS, PASTA_HTML,
    ARQUIVO_JSON, ANTECEDENCIA_DIAS
)


def configurar_logging():
    """Configura o logging global da aplicação."""
    os.makedirs(PASTA_SCREENSHOTS, exist_ok=True)
    os.makedirs(PASTA_HTML, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(threadName)s] %(levelname)s - %(message)s"
    )


def salvar_screenshot(driver, nome: str):
    """Salva screenshot com o nome fornecido."""
    try:
        os.makedirs(PASTA_SCREENSHOTS, exist_ok=True)
        path = os.path.join(PASTA_SCREENSHOTS, f"{nome}.png")
        driver.save_screenshot(path)
        logging.info(f"[SCREENSHOT] Salvo: {path}")
    except Exception as e:
        logging.error(f"[SCREENSHOT] Falha ao salvar '{nome}': {e}")


def diagnosticar_pagina(driver, contexto: str):
    """Salva título, URL e HTML da página atual para debug."""
    try:
        title = driver.title
        url = driver.current_url
        logging.info(f"[DIAGNOSTICO] {contexto} | Title: {title[:80]} | URL: {url}")
        os.makedirs(PASTA_HTML, exist_ok=True)
        html_path = os.path.join(PASTA_HTML, f"{contexto}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logging.info(f"[DIAGNOSTICO] HTML salvo: {html_path}")
        salvar_screenshot(driver, contexto)
    except Exception as e:
        logging.warning(f"[DIAGNOSTICO] Falha: {e}")


def salvar_em_json(dados: dict, arquivo: str = ARQUIVO_JSON):
    """
    Salva dados de uma publicação em arquivo JSON com deduplicação por processo_numero.
    Se processo_numero for N/A, usa hash do conteúdo como ID temporário.
    """
    processo = dados.get("processo_numero")

    if not processo or processo == "N/A":
        conteudo = dados.get("conteudo", "")
        if conteudo:
            hash_id = "TMP-" + hashlib.md5(conteudo.encode("utf-8")).hexdigest()[:12].upper()
            dados["processo_numero"] = hash_id
            dados["processo_numero_origem"] = "hash_conteudo"
            processo = hash_id
            logging.warning(
                f"[SALVAR] Processo N/A — ID temporário gerado: {hash_id}. "
                "Verifique manualmente o número do processo."
            )
        else:
            logging.warning("[SALVAR] Processo N/A e sem conteúdo. Registro descartado.")
            return

    os.makedirs(os.path.dirname(arquivo), exist_ok=True)

    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            publicacoes = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        publicacoes = []

    for i, pub in enumerate(publicacoes):
        if pub.get("processo_numero") == processo:
            publicacoes[i] = dados
            break
    else:
        publicacoes.append(dados)

    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(publicacoes, f, ensure_ascii=False, indent=2)

    logging.info(f"[SALVAR] Publicação salva: {processo}")


def calcular_datas_agendamento(prazo_dias: int, data_str: str) -> dict | None:
    """
    Calcula as datas de agendamento com base no prazo e data de disponibilização.

    Returns:
        dict com data_limite, data_agendamento, status_temporal, dias_restantes
        ou None se a data não puder ser interpretada.
    """
    if data_str:
        match = re.search(
            r"(\d{2}/\d{2}/\d{4})|(\d{4}-\d{2}-\d{2})|(\d{2}/\d{2}/\d{2})",
            data_str
        )
        if match:
            data_str = match.group(0)

    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
        try:
            data_disp = datetime.strptime(data_str, fmt)
            break
        except ValueError:
            continue
    else:
        logging.warning(f"[DATAS] Formato de data não reconhecido: '{data_str}'")
        return None

    hoje = datetime.now()
    data_limite = data_disp + timedelta(days=prazo_dias * 1.4)   # Aprox. dias úteis
    data_agendamento = data_limite - timedelta(days=ANTECEDENCIA_DIAS)
    dias_restantes = (data_agendamento - hoje).days

    if data_agendamento < hoje:
        status_temporal = "ATRASADO"
    elif dias_restantes <= 2:
        status_temporal = "URGENTE"
    else:
        status_temporal = "OK"

    return {
        "data_limite": data_limite.strftime("%d/%m/%Y"),
        "data_agendamento": data_agendamento.strftime("%d/%m/%Y"),
        "status_temporal": status_temporal,
        "dias_restantes": dias_restantes,
    }


def extrair_retry_delay(error_msg: str, default: int = 5) -> int:
    """Tenta extrair o tempo de espera sugerido pela API em mensagens de rate limit."""
    match = re.search(r"retryDelay.*?(\d+)s|(\d+)\s*seconds", error_msg, re.IGNORECASE)
    if match:
        return int(match.group(1) or match.group(2)) + 1
    return default


def normalizar_key(label: str) -> str:
    """Converte 'Número único' → 'numero_unico'."""
    nkfd = unicodedata.normalize("NFKD", label)
    sem_acentos = "".join(c for c in nkfd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sem_acentos.lower().strip())
