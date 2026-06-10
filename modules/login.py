#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/login.py
----------------
Login no Thomson Reuters OnePass / Legal One.
"""

import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException

from config.settings import URL_LOGIN, USERNAME, PASSWORD, TIMEOUT, TIMEOUT_POS_LOGIN, DOMINIOS_VALIDOS


def login_thomson_reuters(driver, user: str = USERNAME, password: str = PASSWORD):
    """
    Realiza o login no Thomson Reuters OnePass e aguarda redirecionamento
    para um dos domínios válidos (Legal One / NovaJus).

    Args:
        driver: WebDriver configurado.
        user: Nome de usuário (padrão: USERNAME do settings).
        password: Senha (padrão: PASSWORD do settings).

    Raises:
        TimeoutException: Se o login não for concluído no tempo esperado.
    """
    logging.info(f"[LOGIN] Acessando página de login: {URL_LOGIN[:60]}...")
    driver.get(URL_LOGIN)

    wait = WebDriverWait(driver, TIMEOUT)

    # Preenche usuário
    campo_user = wait.until(EC.presence_of_element_located((By.ID, "Username")))
    campo_user.clear()
    campo_user.send_keys(user)

    # Preenche senha
    campo_pass = driver.find_element(By.ID, "Password")
    campo_pass.clear()
    campo_pass.send_keys(password)

    # Clica em "Sign In"
    btn_signin = wait.until(EC.element_to_be_clickable((By.ID, "SignIn")))
    driver.execute_script("arguments[0].scrollIntoView(true);", btn_signin)
    try:
        btn_signin.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", btn_signin)

    # Aguarda redirecionamento para domínio válido
    wait_pos = WebDriverWait(driver, TIMEOUT_POS_LOGIN)
    wait_pos.until(
        lambda d: any(dom in d.current_url for dom in DOMINIOS_VALIDOS)
    )

    logging.info(f"[LOGIN] ✅ Login bem-sucedido! URL: {driver.current_url}")
