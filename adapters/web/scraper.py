import re
import time
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from datetime import datetime

from adapters.infra.logging_utils import salvar_screenshot


def _normalizar_key(label: str) -> str:
    import unicodedata
    nkfd = unicodedata.normalize("NFKD", label)
    sem_acentos = "".join(c for c in nkfd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sem_acentos.lower().strip())


def parse_conteudo_dinamico(texto: str) -> dict:
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

        adv_match = adv_regex.match(linha)
        if adv_match:
            nome, oab = adv_match.groups()
            advogados.append({"nome": nome.strip(), "oab": oab.strip()})
            continue

        campo_match = campo_regex.match(linha)
        if campo_match:
            if ultimo_label:
                campos[_normalizar_key(ultimo_label)] = " | ".join(valor_atual).strip()
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
            valor_atual.append(linha.strip())
        else:
            if ultimo_label:
                campos[_normalizar_key(ultimo_label)] = " | ".join(valor_atual).strip()
            ultimo_label = None
            valor_atual = []

    if ultimo_label:
        campos[_normalizar_key(ultimo_label)] = " | ".join(valor_atual).strip()

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
    cnj_patterns = [
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{4}",
        r"\d{7}-\d{2}\.\d{4}\.\d{2}\.\d{4}",
    ]

    for pattern in cnj_patterns:
        match = re.search(pattern, texto)
        if match:
            return match.group(0)

    num_match = re.search(r"[Nn][uú]mero\s+[uú]nico[:\s]+([\d]{20})", texto)
    if num_match:
        raw = num_match.group(1)
        try:
            cnj = f"{raw[0:7]}-{raw[7:9]}.{raw[9:13]}.{raw[13]}.{raw[14:16]}.{raw[16:20]}"
            logging.info(f"[SCRAPER] Numero unico convertido para CNJ: {cnj}")
            return cnj
        except Exception:
            return raw

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
                        logging.info(f"[SCRAPER] Processo extraido do DOM: {m.group(0)}")
                        return m.group(0)
        except Exception:
            pass

    return "N/A"


def _extrair_advogados(conteudo: str) -> list:
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

    wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div[role='tabpanel'].collapse.show, div.formatted-text")
        )
    )
    time.sleep(1)

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
    dados["processo_numero"] = _extrair_numero_cnj(conteudo, driver)

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

    data_match = re.search(
        r"dia\s+(\d{2}/\d{2}/\d{4})|em\s+(\d{2}/\d{2}/\d{4})",
        conteudo, re.IGNORECASE
    )
    if data_match:
        dados["data_disponibilizacao"] = data_match.group(1) or data_match.group(2)

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

    dados["advogados"] = _extrair_advogados(conteudo)
    dados["conteudo_parsed"] = parse_conteudo_dinamico(conteudo)

    logging.info(
        f"[SCRAPER] Processo: {dados['processo_numero']} | "
        f"Conteudo: {len(conteudo)} chars | "
        f"Advogados: {len(dados['advogados'])}"
    )

    return dados