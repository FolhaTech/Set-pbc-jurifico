import time
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementClickInterceptedException,
)

from config.settings import TIMEOUT, DOMINIOS_VALIDOS, RESPONSAVEL_ALVO


def acessar_publicacoes(driver):
    time.sleep(8)

    current_url = driver.current_url.lower()
    if "publicacoes" in current_url or "publications" in current_url:
        logging.info("[NAV] Ja em Publicacoes.")
        return

    wait = WebDriverWait(driver, TIMEOUT)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    try:
        menu = wait.until(EC.element_to_be_clickable((By.ID, "menuPublicationManagement")))
        href = menu.get_attribute("href")
        if href and any(dom in href for dom in DOMINIOS_VALIDOS):
            driver.get(href)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.publication-items")))
            logging.info("[NAV] Publicacoes via href do menu.")
            return
    except Exception:
        pass

    try:
        menu = driver.find_element(By.ID, "menuPublicationManagement")
        driver.execute_script("arguments[0].click();", menu)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.publication-items")))
        logging.info("[NAV] Publicacoes via clique no menu.")
        return
    except Exception:
        pass

    seletores = [
        (By.XPATH, "//a[normalize-space(text())='Publicacoes']"),
        (By.XPATH, "//a[contains(@href, '/publicacoes')]"),
        (By.CSS_SELECTOR, "a[href*='publicacoes']"),
    ]
    for by, sel in seletores:
        try:
            el = wait.until(EC.element_to_be_clickable((by, sel)))
            driver.execute_script("arguments[0].scrollIntoView(true);", el)
            try:
                el.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(3)
            if any(w in driver.current_url.lower() for w in ["publicacoes", "publications"]):
                logging.info(f"[NAV] Publicacoes via seletor: {sel}")
                return
        except (TimeoutException, NoSuchElementException):
            continue

    driver.get("https://firm.legalone.com.br/publications")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.publication-items")))
    logging.info("[NAV] Publicacoes via URL hardcoded.")


def selecionar_periodo_60_dias(driver):
    logging.info("[FILTRO] Selecionando periodo: Ultimos 60 dias...")
    wait = WebDriverWait(driver, TIMEOUT)

    try:
        btn_date = wait.until(EC.element_to_be_clickable((By.ID, "btnDateFilterSplit")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn_date)
        time.sleep(0.5)
        try:
            btn_date.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", btn_date)

        time.sleep(1)

        btn_60 = wait.until(EC.element_to_be_clickable((By.ID, "btnChangeReceivedOn-60")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn_60)
        try:
            btn_60.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", btn_60)

        time.sleep(2)
        logging.info("[FILTRO] Periodo 60 dias selecionado.")
    except Exception as e:
        logging.warning(f"[FILTRO] Nao foi possivel selecionar 60 dias: {e}")


def abrir_mais_filtros(driver):
    seletores = [
        (By.ID, "sidebar-collapse-button"),
        (By.XPATH, "//button[contains(text(),'Mais filtros')]"),
        (By.CSS_SELECTOR, "[data-toggle='collapse']"),
        (By.CSS_SELECTOR, "button[id*='filter']"),
    ]
    for by, sel in seletores:
        try:
            el = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, sel)))
            driver.execute_script("arguments[0].scrollIntoView(true);", el)
            try:
                el.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", el)
            logging.info(f"[FILTRO] Mais filtros abertos [{sel}].")
            time.sleep(1)
            return
        except (TimeoutException, NoSuchElementException):
            continue

    logging.warning("[FILTRO] Painel 'Mais filtros' nao encontrado — continuando.")


def selecionar_responsavel(driver, nome: str = RESPONSAVEL_ALVO):
    wait = WebDriverWait(driver, TIMEOUT)

    campo_id = "publication-multiselect-filter-with-search-select-responsible-user-filter"
    try:
        campo = wait.until(EC.presence_of_element_located((By.ID, campo_id)))
    except TimeoutException:
        logging.warning("[FILTRO] Campo 'Responsavel' nao encontrado pelo ID.")
        return

    driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", campo)
    time.sleep(2)

    option_xpath = (
        f"//label[contains(@class,'lookup-option-label') and normalize-space(text())='{nome}']"
    )
    try:
        option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
        driver.execute_script("arguments[0].click();", option)
        time.sleep(1)
        logging.info(f"[FILTRO] Responsavel '{nome}' selecionado.")
    except TimeoutException:
        logging.warning(f"[FILTRO] Responsavel '{nome}' nao encontrado na lista.")


def aplicar_filtros(driver):
    wait = WebDriverWait(driver, 30)

    seletores = [
        (By.ID, "publication-apply-filter-button"),
        (By.XPATH, "//button[contains(text(),'Aplicar') or contains(text(),'Apply')]"),
    ]
    for by, sel in seletores:
        try:
            btn = wait.until(EC.element_to_be_clickable((by, sel)))
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            try:
                btn.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", btn)

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.publication-items")))
            logging.info("[FILTRO] Filtros aplicados.")
            return
        except Exception:
            continue

    logging.warning("[FILTRO] Botao 'Aplicar' nao encontrado.")