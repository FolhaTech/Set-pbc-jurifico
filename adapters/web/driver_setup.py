import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

UC_DISPONIVEL = False
try:
    import undetected_chromedriver as uc
    UC_DISPONIVEL = True
    uc.Chrome.__del__ = lambda self: None
except ImportError:
    pass


def _detectar_versao_chrome() -> int | None:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Google\Chrome\BLBeacon"
        )
        version, _ = winreg.QueryValueEx(key, "version")
        version_main = int(version.split(".")[0])
        logging.info(f"[DRIVER] Chrome detectado (HKCU): versao {version_main}")
        return version_main
    except Exception:
        pass

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome"
        )
        version, _ = winreg.QueryValueEx(key, "DisplayVersion")
        version_main = int(version.split(".")[0])
        logging.info(f"[DRIVER] Chrome detectado (HKLM): versao {version_main}")
        return version_main
    except Exception:
        pass

    logging.warning("[DRIVER] Versao do Chrome nao detectada. Usando fallback 148.")
    return 148


def _opcoes_undetected() -> "uc.ChromeOptions":
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return options


def _opcoes_selenium_padrao() -> Options:
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return options


def configurar_driver(usar_undetected: bool = True):
    if usar_undetected and UC_DISPONIVEL:
        logging.info("[DRIVER] Iniciando undetected_chromedriver...")
        version_main = _detectar_versao_chrome()
        options = _opcoes_undetected()

        try:
            driver = uc.Chrome(options=options, version_main=version_main)
            logging.info("[DRIVER] undetected_chromedriver iniciado com versao detectada.")
        except Exception as e:
            logging.warning(f"[DRIVER] Falha com versao {version_main}: {e}")
            try:
                driver = uc.Chrome(options=options, version_main=None)
                logging.info("[DRIVER] undetected_chromedriver iniciado sem versao.")
            except Exception as e2:
                logging.error(f"[DRIVER] Falha total no undetected_chromedriver: {e2}")
                logging.info("[DRIVER] Recorrendo ao Selenium Chrome padrao...")
                driver = webdriver.Chrome(options=_opcoes_selenium_padrao())
    else:
        logging.info("[DRIVER] Iniciando Selenium Chrome padrao...")
        driver = webdriver.Chrome(options=_opcoes_selenium_padrao())

    try:
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
    except Exception:
        pass

    return driver