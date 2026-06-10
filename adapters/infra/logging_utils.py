import os
import logging

from config.settings import PASTA_SCREENSHOTS, PASTA_HTML


def configurar_logging() -> None:
    os.makedirs(PASTA_SCREENSHOTS, exist_ok=True)
    os.makedirs(PASTA_HTML, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(threadName)s] %(levelname)s - %(message)s",
    )


def salvar_screenshot(driver, nome: str) -> None:
    try:
        os.makedirs(PASTA_SCREENSHOTS, exist_ok=True)
        path = os.path.join(PASTA_SCREENSHOTS, f"{nome}.png")
        driver.save_screenshot(path)
        logging.info(f"[SCREENSHOT] Salvo: {path}")
    except Exception as e:
        logging.error(f"[SCREENSHOT] Falha ao salvar '{nome}': {e}")


def diagnosticar_pagina(driver, contexto: str) -> None:
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