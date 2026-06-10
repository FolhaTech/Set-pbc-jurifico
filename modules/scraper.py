#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/scraper.py
------------------
Raspagem dos detalhes de uma publicação jurídica no Legal One.
Extrai: número do processo, conteúdo, tribunal, diário, data, advogados.
"""

import re
import time
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from datetime import datetime
from modules.utils import normalizar_key, salvar_screenshot


def parse_conteudo_dinamico(texto: str) -> dict:
    """
    Parser genérico que detecta campos 'Label: valor' no texto da publicação.
    Também extrai advogados no formato 'Nome - OAB: NUMERO'.

    Returns:
        dict com: campos, advogados, flags, texto_bruto
    """
    linhas = texto.strip().split("\n")
    campos = {}
    advogados = []
    eh_sigiloso = False
    processo_sigiloso = False
    consulta_autos_digitais = False
    ultimo_label = None
    valor_atual = []

    adv_regex = re.compile(r"^\s*(.+?)\s*-\s*OAB:\s*([\w\d\-/]+)\s*$", re.IGNORECASE)
    campo_regex = re.compile(r"^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9\s/\-]+?)\s*:\s*(.+?)\s*$")

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        # Caso 1: advogado com OAB
        adv_match = adv_regex.match(linha)
        if adv_match:
            nome, oab = adv_match.groups()
            advogados.append({"nome": nome.strip(), "oab": oab.strip()})
            continue

        # Caso 2: campo "Label: valor"
        campo_match = campo_regex.match(linha)
        if campo_match:
            if ultimo_label:
                campos[normalizar_key(ultimo_label)] = " | ".join(valor_atual).strip()
            ultimo_label, valor = campo_match.groups()
            valor_atual = [valor.strip()]
            lbl_lower = ultimo_label.lower()
            if "sigilos" in lbl_lower:
                eh_sigiloso = True
            if "processo sigilos" in lbl_lower:
                processo_sigiloso = True
            if "consulta aos autos" in lbl_lower:
                consulta_autos_digitais = True
        elif linha.startswith("    ") or linha.startswith("   "):
            # linha de continuação (indentada)
            valor_atual.append(linha.strip())
        else:
            if ultimo_label:
                campos[normalizar_key(ultimo_label)] = " | ".join(valor_atual).strip()
            ultimo_label = None
            valor_atual = []

    if ultimo_label:
        campos[normalizar_key(ultimo_label)] = " | ".join(valor_atual).strip()

    return {
        "campos": campos,
        "advogados": advogados,
        "flags": {
            "eh_sigiloso": eh_sigiloso,
            "processo_sigiloso": processo_sigiloso,
            "consulta_autos_digitais": consulta_autos_digitais,
        },
        "texto_bruto": texto,
    }


def _extrair_numero_cnj(texto: str, driver=None) -> str:
    """
    Tenta extrair o número CNJ do processo usando 3 estratégias:
      1. Padrão CNJ com traços no conteúdo
      2. Campo 'Número único' (20 dígitos sem traços)
      3. Link/href do processo no DOM
    """
    cnj_patterns = [
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{4}",
        r"\d{7}-\d{2}\.\d{4}\.\d{2}\.\d{4}",
    ]

    # Estratégia 1: padrão CNJ no texto
    for pattern in cnj_patterns:
        match = re.search(pattern, texto)
        if match:
            return match.group(0)

    # Estratégia 2: número único (20 dígitos) convertido para CNJ
    num_match = re.search(r"[Nn][uú]mero\s+[uú]nico[:\s]+([\d]{20})", texto)
    if num_match:
        raw = num_match.group(1)
        try:
            cnj = f"{raw[0:7]}-{raw[7:9]}.{raw[9:13]}.{raw[13]}.{raw[14:16]}.{raw[16:20]}"
            logging.info(f"[SCRAPER] Número único convertido para CNJ: {cnj}")
            return cnj
        except Exception:
            return raw

    # Estratégia 3: DOM (link do processo)
    if driver:
        try:
            link = driver.find_element(
                By.CSS_SELECTOR,
                "a[href*='processo'], a[id*='processo'], .publication-detail a[href*='/processo/']"
            )
            for src in [link.get_attribute("href") or "", link.text or ""]:
                for pattern in cnj_patterns:
                    m = re.search(pattern, src)
                    if m:
                        logging.info(f"[SCRAPER] Processo extraído do DOM: {m.group(0)}")
                        return m.group(0)
        except Exception:
            pass

    return "N/A"


def _extrair_advogados(conteudo: str) -> list:
    """
    Extrai lista de advogados no formato 'Nome - OAB/UF' do conteúdo.
    """
    advogados = []
    bloco_matches = re.findall(
        r"Advogado:\s*(.*?)(?:\. Relator:|\. Agravado:|\. Agravante:|$)",
        conteudo,
        re.IGNORECASE | re.DOTALL,
    )
    for bloco in bloco_matches:
        for item in bloco.split(","):
            item = item.strip().strip(".")
            match = re.search(r"(.+?)\s*-\s*([\dA-Z]+N?-[A-Z]{2})", item)
            if match:
                advogados.append({
                    "nome": match.group(1).strip(),
                    "oab": match.group(2).strip(),
                })
    return advogados


def raspar_detalhes_publicacao(driver) -> dict:
    """
    Raspa todos os detalhes da publicação atualmente aberta no painel de detalhes.

    Returns:
        dict com: url_pagina, data_raspagem, processo_numero, processo_href,
                  tipo, badge, data_disponibilizacao, fonte_tribunal, fonte_diario,
                  conteudo, conteudo_parsed, advogados
    """
    wait = WebDriverWait(driver, 20)

    dados = {
        "url_pagina": driver.current_url,
        "data_raspagem": datetime.now().isoformat(),
        "processo_numero": "N/A",
        "processo_href": None,
        "tipo": "N/A",
        "badge": "N/A",
        "data_disponibilizacao": "N/A",
        "fonte_tribunal": "N/A",
        "fonte_diario": "N/A",
        "conteudo": "",
        "conteudo_parsed": {},
        "advogados": [],
    }

    # Aguarda o painel de detalhes ou conteúdo estar presente
    wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div[role='tabpanel'].collapse.show, div.formatted-text")
        )
    )
    time.sleep(1)

    # ── Extração do conteúdo principal ──────────────────────────────────────
    conteudo = ""
    seletores_conteudo = [
        "div[role='tabpanel'].collapse.show div.formatted-text",
        "div.card-body div.formatted-text",
        "div.formatted-text",
        ".publication-detail div.formatted-text",
    ]
    for seletor in seletores_conteudo:
        try:
            elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
            for el in elementos:
                texto = driver.execute_script(
                    "return arguments[0].innerText || arguments[0].textContent;", el
                )
                if texto and len(texto.strip()) > 50:
                    conteudo = texto.strip()
                    break
            if conteudo:
                break
        except Exception:
            continue

    dados["conteudo"] = conteudo

    # ── Número do processo ───────────────────────────────────────────────────
    dados["processo_numero"] = _extrair_numero_cnj(conteudo, driver)

    # ── Fonte do rodapé ──────────────────────────────────────────────────────
    try:
        dados["fonte_tribunal"] = driver.find_element(
            By.ID, "publication-detail-footer-sourceCourt"
        ).text.strip()
    except Exception:
        pass

    try:
        dados["fonte_diario"] = driver.find_element(
            By.ID, "publication-detail-footer-source"
        ).text.strip()
    except Exception:
        pass

    # ── Data de disponibilização (extraída do conteúdo) ──────────────────────
    data_match = re.search(
        r"dia\s+(\d{2}/\d{2}/\d{4})|em\s+(\d{2}/\d{2}/\d{4})",
        conteudo, re.IGNORECASE
    )
    if data_match:
        dados["data_disponibilizacao"] = data_match.group(1) or data_match.group(2)

    # ── Badge e tipo ─────────────────────────────────────────────────────────
    try:
        dados["badge"] = driver.find_element(
            By.CSS_SELECTOR, "span.badge.badge-light"
        ).text.strip()
    except Exception:
        pass

    try:
        dados["tipo"] = driver.find_element(
            By.CSS_SELECTOR, "span.type-field-value"
        ).text.strip()
    except Exception:
        pass

    # ── Advogados ────────────────────────────────────────────────────────────
    dados["advogados"] = _extrair_advogados(conteudo)

    # ── Parser dinâmico do conteúdo ──────────────────────────────────────────
    dados["conteudo_parsed"] = parse_conteudo_dinamico(conteudo)

    logging.info(
        f"[SCRAPER] Processo: {dados['processo_numero']} | "
        f"Conteúdo: {len(conteudo)} chars | "
        f"Advogados: {len(dados['advogados'])}"
    )

    return dados
