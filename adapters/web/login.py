import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException

from config.settings import URL_LOGIN, USERNAME, PASSWORD, TIMEOUT, TIMEOUT_POS_LOGIN, DOMINIOS_VALIDOS


def login_thomson_reuters(driver, user: str = USERNAME, password: str = PASSWORD):
    logging.info(f"[LOGIN] Acessando pagina de login: {URL_LOGIN[:60]}...")
    driver.get(URL_LOGIN)

    wait = WebDriverWait(driver, TIMEOUT)

    campo_user = wait.until(EC.presence_of_element_located((By.ID, "Username")))
    campo_user.clear()
    campo_user.send_keys(user)

    campo_pass = driver.find_element(By.ID, "Password")
    campo_pass.clear()
    campo_pass.send_keys(password)

    btn_signin = wait.until(EC.element_to_be_clickable((By.ID, "SignIn")))
    driver.execute_script("arguments[0].scrollIntoView(true);", btn_signin)
    try:
        btn_signin.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", btn_signin)

    wait_pos = WebDriverWait(driver, TIMEOUT_POS_LOGIN)
    wait_pos.until(
        lambda d: any(dom in d.current_url for dom in DOMINIOS_VALIDOS)
    )

    logging.info(f"[LOGIN] Login bem-sucedido! URL: {driver.current_url}")