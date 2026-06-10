import time
import logging
import uuid

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from adapters.infra.logging_utils import salvar_screenshot


def clicar_elemento_seguro(driver, elemento) -> bool:
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", elemento
        )
        time.sleep(0.5)
        try:
            elemento.click()
        except Exception:
            driver.execute_script("arguments[0].click();", elemento)
        return True
    except Exception as e:
        logging.warning(f"[ACAO] Falha ao clicar no elemento: {e}")
        return False


def abrir_dropdown_status(driver) -> bool:
    time.sleep(1)

    xpaths = [
        "//button[normalize-space(.)='Pendente']",
        "//button[contains(.,'Pendente')]",
        "//*[@id='publication-detail-status-btn']",
        "//button[contains(@id,'status')]",
        "//button[contains(@class,'status')]",
        "//div[contains(@class,'publication')]//button[contains(@class,'btn')]",
    ]
    for xp in xpaths:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            btn.click()
            time.sleep(1.5)
            logging.info(f"[ACAO] Dropdown aberto via XPath: {xp}")
            return True
        except Exception:
            continue

    css_seletores = [
        "#publication-detail-status-btn",
        "button[id*='status']",
        "button.dropdown-toggle",
        ".publication-status button",
    ]
    for sel in css_seletores:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.5)
            logging.info(f"[ACAO] Dropdown aberto via CSS: {sel}")
            return True
        except Exception:
            continue

    salvar_screenshot(driver, "debug_dropdown_nao_encontrado")
    logging.warning("[ACAO] Nao foi possivel abrir o dropdown de status.")
    return False


def _clicar_opcao_menu(driver, texto_alvo: str, nome_acao: str) -> bool:
    time.sleep(1.5)

    xpaths = [
        f"//a[contains(normalize-space(.), '{texto_alvo}')]",
        f"//li[contains(normalize-space(.), '{texto_alvo}')]",
        f"//button[contains(normalize-space(.), '{texto_alvo}')]",
        f"//span[contains(normalize-space(.), '{texto_alvo}')]",
        f"//*[contains(normalize-space(text()), '{texto_alvo}')]",
    ]
    for xp in xpaths:
        try:
            elementos = driver.find_elements(By.XPATH, xp)
            for el in elementos:
                texto = (el.text or el.get_attribute("innerText") or "").strip()
                if texto_alvo.lower() in texto.lower() and el.is_displayed():
                    if clicar_elemento_seguro(driver, el):
                        logging.info(f"[ACAO] '{nome_acao}' clicado via XPath.")
                        time.sleep(2)
                        return True
        except Exception:
            continue

    try:
        result = driver.execute_script(f"""
            var alvo = '{texto_alvo}'.toLowerCase();
            var todos = document.querySelectorAll('a, li, button, span, div');
            for (var i = 0; i < todo.length; i++) {{
                var txt = (todos[i].innerText || '').toLowerCase().trim();
                if ((txt === alvo || txt.includes(alvo)) && todos[i].offsetParent !== null) {{
                    todos[i].click();
                    return txt;
                }}
            }}
            return null;
        """)
        if result:
            logging.info(f"[ACAO] '{nome_acao}' clicado via JavaScript: '{result}'")
            time.sleep(2)
            return True
    except Exception as e:
        logging.warning(f"[ACAO] Falha JS para '{texto_alvo}': {e}")

    salvar_screenshot(
        driver, f"debug_{nome_acao.lower().replace(' ', '_')}_nao_encontrado"
    )
    logging.warning(f"[ACAO] Opcao '{texto_alvo}' nao encontrada no menu.")
    return False


def marcar_tratado(driver) -> bool:
    try:
        if not abrir_dropdown_status(driver):
            logging.warning(
                "[ACAO] Dropdown nao aberto. Nao foi possivel marcar 'Tratado'."
            )
            return False

        for texto in ["Tratado", "tratado", "TRATADO"]:
            if _clicar_opcao_menu(driver, texto, "Tratado"):
                logging.info("[ACAO] Marcado como 'Tratado'.")
                return True

        return False
    except Exception as e:
        logging.warning(f"[ACAO] Falha em marcar_tratado: {e}")
        return False


def marcar_sem_providencia(driver) -> bool:
    try:
        if not abrir_dropdown_status(driver):
            logging.warning(
                "[ACAO] Dropdown nao aberto. Nao foi possivel marcar 'Sem providencias'."
            )
            return False

        time.sleep(1)

        xpaths_exatos = [
            "//button[contains(@class, 'dropdown-item') and contains(., 'Sem providências')]",
            "//button[.//svg[contains(@class, 'no-providence-icon')]]",
            "//button[contains(normalize-space(.), 'Sem providências')]",
        ]
        for xp in xpaths_exatos:
            try:
                elementos = driver.find_elements(By.XPATH, xp)
                for el in elementos:
                    if el.is_displayed():
                        if clicar_elemento_seguro(driver, el):
                            logging.info("[ACAO] 'Sem providencias' via XPath exato.")
                            time.sleep(2)
                            return True
            except Exception:
                continue

        for texto in ["Sem providências", "Sem providência", "Sem providencia"]:
            if _clicar_opcao_menu(driver, texto, "Sem providencias"):
                logging.info("[ACAO] Marcado como 'Sem providencias'.")
                return True

        return False
    except Exception as e:
        logging.warning(f"[ACAO] Falha em marcar_sem_providencia: {e}")
        return False


def obter_classificacao_ia(dados: dict, opcoes: list, adapta_info: dict | None) -> str:
    if not adapta_info:
        logging.warning(
            "[ACAO] Adapta ONE nao disponivel para classificacao de descricao. Pulando."
        )
        return "N/A"

    prompt = (
            f"Com base na publicacao juridica abaixo, identifique qual das seguintes opcoes de descricao de compromisso "
            f"do escritorio e a mais adequada.\n\n"
            f"**PUBLICACAO:**\n{dados.get('conteudo', '')}\n\n"
            f"**OPCOES DISPONIVEIS:**\n" + "\n".join(f"- {op}" for op in opcoes) + "\n\n"
                                                                                   f"Responda APENAS com o texto exato da opcao selecionada (copie exatamente como esta na lista acima). "
                                                                                   f"Nao adicione introducao, pontuacao, explicacao ou qualquer texto extra. "
                                                                                   f"Se nenhuma opcao se aplicar, responda exatamente: N/A"
    )

    try:
        client = adapta_info["client"]

        logging.info(
            "[ACAO] Enviando lista de descricoes ao expert do Adapta ONE para classificacao..."
        )

        escolha_raw = client._enviar_prompt(prompt).strip()
        logging.info(f"[ACAO] Expert Adapta ONE respondeu: '{escolha_raw[:200]}...'")

        linas = [l.strip() for l in escolha_raw.splitlines() if l.strip()]

        for linha in reversed(linhas):
            if linha in opcoes:
                logging.info(f"[ACAO] Correspondencia exata (ultima linha): '{linha}'")
                return linha

        for linha in reversed(linhas):
            for op in opcoes:
                if op.lower() in linha.lower():
                    logging.info(f"[ACAO] Correspondencia parcial encontrada: '{op}'")
                    return op

        for op in opcoes:
            if op.lower() in escolha_raw.lower():
                logging.info(f"[ACAO] Correspondencia no texto completo: '{op}'")
                return op
    except Exception as e:
        logging.warning(f"[ACAO] Falha ao obter classificacao via IA: {e}")
    return "N/A"


def clicar_link_processo(driver, dados: dict = None, adapta_info: dict = None) -> bool:
    logging.info("[ACAO] Tentando clicar no link do processo para abrir em nova aba...")

    original_handle = driver.current_window_handle
    total_abas_antes = len(driver.window_handles)

    seletores = [
        (By.XPATH, "//span[contains(text(), 'Pasta/Contato')]/following-sibling::a"),
        (By.XPATH, "//span[contains(text(), 'Processo')]/following-sibling::a"),
        (By.CSS_SELECTOR, "a[href*='/processos/processos/Details/']"),
        (By.CSS_SELECTOR, "a[href*='/processos/details/']"),
    ]

    link_clicado = False
    for by, sel in seletores:
        try:
            elementos = driver.find_elements(by, sel)
            for el in elementos:
                if el.is_displayed():
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", el
                    )
                    time.sleep(0.5)
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    logging.info(f"[ACAO] Link do processo clicado via seletor: {sel}")
                    link_clicado = True
                    break
            if link_clicado:
                break
        except Exception as e:
            logging.warning(f"[ACAO] Erro ao tentar clicar com seletor {sel}: {e}")
            continue

    if not link_clicado:
        logging.warning(
            "[ACAO] Nao foi possivel encontrar ou clicar no link do processo."
        )
        return False

    try:
        WebDriverWait(driver, 10).until(
            lambda d: len(d.window_handles) > total_abas_antes
        )
        novas_abas = [h for h in driver.window_handles if h != original_handle]
        if novas_abas:
            new_handle = novas_abas[-1]
            driver.switch_to.window(new_handle)
            logging.info("[ACAO] Mudou para a nova aba do processo.")
            time.sleep(5)

            wait = WebDriverWait(driver, 15)

            tab_comp = wait.until(
                EC.element_to_be_clickable((By.ID, "aTab-appointments-and-tasks"))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", tab_comp
            )
            time.sleep(0.5)
            try:
                tab_comp.click()
            except Exception:
                driver.execute_script("arguments[0].click();", tab_comp)
            logging.info("[ACAO] Aba 'Compromissos e tarefas' selecionada.")
            time.sleep(3)

            btn_adicionar = wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//span[contains(@class, 'add-popover-menu') and (contains(text(), 'Adicionar') or contains(text(), 'Add'))]",
                    )
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", btn_adicionar
            )
            time.sleep(0.5)

            driver.execute_script(
                "var ev1 = new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window });"
                "var ev2 = new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window });"
                "arguments[0].dispatchEvent(ev1);"
                "arguments[0].dispatchEvent(ev2);",
                btn_adicionar,
            )

            try:
                from selenium.webdriver.common.action_chains import ActionChains

                actions = ActionChains(driver)
                actions.move_to_element(btn_adicionar).perform()
            except Exception:
                pass

            logging.info("[ACAO] Mouse posicionado (hover) sobre o botao 'Adicionar'.")
            time.sleep(1.5)

            link_clicado_comp = False
            try:
                link_novo = WebDriverWait(driver, 4).until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//a[contains(text(), 'Novo compromisso') or contains(@href, '/processos/compromissos/CreateFromProcesso/')]",
                        )
                    )
                )
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", link_novo
                )
                time.sleep(0.5)
                link_novo.click()
                link_clicado_comp = True
            except Exception:
                logging.info(
                    "[ACAO] Click convencional nao funcionou, tentando click direto via JavaScript..."
                )

            if not link_clicado_comp:
                resultado_js = driver.execute_script("""
                    var links = document.querySelectorAll("a[href*='/processos/compromissos/CreateFromProcesso/']");
                    for (var i = 0; i < links.length; i++) {
                        links[i].scrollIntoView({block: 'center'});
                        links[i].click();
                        return true;
                    }
                    var allLinks = document.querySelectorAll("a");
                    for (var i = 0; i < allLinks.length; i++) {
                        if (allLinks[i].innerText.trim() === 'Novo compromisso') {
                            allLinks[i].scrollIntoView({block: 'center'});
                            allLinks[i].click();
                            return true;
                        }
                    }
                    return false;
                """)
                if resultado_js:
                    link_clicado_comp = True

            if link_clicado_comp:
                logging.info(
                    "[ACAO] Link 'Novo compromisso' clicado. Aguardando tela de criacao..."
                )
                time.sleep(3)
            else:
                raise Exception(
                    "Nao foi possivel encontrar ou clicar no link 'Novo compromisso'."
                )

            logging.info("[ACAO] Aguardando campo 'Descricao' carregar na tela...")
            input_descricao = wait.until(
                EC.presence_of_element_located((By.ID, "Descricao"))
            )
            time.sleep(2)

            logging.info(
                "[ACAO] Localizando e clicando no botao de lookup para 'Descricao'..."
            )
            xpath_lookup_btn = "//div[contains(@class, 'lookup') and .//input[@id='Descricao']]//div[contains(@class, 'lookup-modal-button')]"
            btn_lookup = wait.until(
                EC.element_to_be_clickable((By.XPATH, xpath_lookup_btn))
            )
            try:
                btn_lookup.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_lookup)
            logging.info("[ACAO] Botao de lookup clicado.")
            time.sleep(2.5)

            logging.info("[ACAO] Aguardando dropdown/modal de lookup de Descricao...")
            xpath_dropdown = (
                "//div[contains(@id, 'lookup_') and contains(@id, '_dropdown')]"
            )
            dropdown = wait.until(
                EC.presence_of_element_located((By.XPATH, xpath_dropdown))
            )

            opcoes = []
            paginas_visitadas = 0
            while paginas_visitadas < 5:
                rows = dropdown.find_elements(
                    By.XPATH, ".//div[@class='lookup-wrapper']//tr[@data-val-id]"
                )
                for row in rows:
                    try:
                        td = row.find_element(
                            By.XPATH, ".//td[@data-val-field='Value']"
                        )
                        texto = td.text.strip()
                        if texto and texto not in opcoes:
                            opcoes.append(texto)
                    except Exception:
                        continue

                try:
                    btn_next = dropdown.find_element(
                        By.XPATH, ".//a[contains(@class, 'paginator-next')]"
                    )
                    if not btn_next.is_displayed():
                        break
                    try:
                        btn_next.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn_next)
                    time.sleep(1.0)
                    paginas_visitadas += 1
                except Exception:
                    break

            logging.info(
                f"[ACAO] Coletadas {len(opcoes)} opcoes de descricao para classificacao."
            )

            escolha = "N/A"
            if dados and opcoes:
                escolha = obter_classificacao_ia(dados, opcoes, adapta_info)

            logging.info(f"[ACAO] Descricao selecionada pela IA: '{escolha}'")

            if escolha and escolha != "N/A" and escolha in opcoes:
                try:

                    def _tentar_clicar_linhas(linhas):
                        for row in linhas:
                            try:
                                td = row.find_element(
                                    By.XPATH, ".//td[@data-val-field='Value']"
                                )
                                texto_td = td.text.strip()
                                if texto_td.lower() == escolha.lower():
                                    driver.execute_script(
                                        "arguments[0].scrollIntoView({block:'center'});",
                                        row,
                                    )
                                    time.sleep(0.4)
                                    try:
                                        row.click()
                                    except Exception:
                                        driver.execute_script(
                                            "arguments[0].click();", row
                                        )
                                    logging.info(
                                        f"[ACAO] Opcao selecionada e clicada no lookup: '{escolha}'"
                                    )
                                    return True
                            except Exception:
                                continue
                        for row in linhas:
                            try:
                                td = row.find_element(
                                    By.XPATH, ".//td[@data-val-field='Value']"
                                )
                                texto_td = td.text.strip()
                                if (
                                        escolha.lower() in texto_td.lower()
                                        or texto_td.lower() in escolha.lower()
                                ):
                                    driver.execute_script(
                                        "arguments[0].scrollIntoView({block:'center'});",
                                        row,
                                    )
                                    time.sleep(0.4)
                                    try:
                                        row.click()
                                    except Exception:
                                        driver.execute_script(
                                            "arguments[0].click();", row
                                        )
                                    logging.info(
                                        f"[ACAO] Opcao parcial clicada no lookup: '{texto_td}'"
                                    )
                                    return True
                            except Exception:
                                continue
                        return False

                    from selenium.webdriver.common.keys import Keys

                    try:
                        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                        time.sleep(1.0)
                    except Exception:
                        pass

                    xpath_lookup_btn2 = "//div[contains(@class, 'lookup') and .//input[@id='Descricao']]//div[contains(@class, 'lookup-modal-button')]"
                    btn_lookup2 = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_lookup_btn2))
                    )
                    try:
                        btn_lookup2.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn_lookup2)
                    logging.info("[ACAO] Lookup reaberto. Aguardando dropdown...")
                    time.sleep(2.5)

                    xpath_dropdown2 = (
                        "//div[contains(@id, 'lookup_') and contains(@id, '_dropdown')]"
                    )
                    dropdown2 = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, xpath_dropdown2))
                    )

                    clicou_opcao = False
                    for pagina in range(6):
                        time.sleep(1.0)
                        linhas_pg = dropdown2.find_elements(
                            By.XPATH,
                            ".//div[@class='lookup-wrapper']//tr[@data-val-id]",
                        )
                        clicou_opcao = _tentar_clicar_linhas(linhas_pg)
                        if clicou_opcao:
                            break
                        try:
                            btn_next2 = dropdown2.find_element(
                                By.XPATH, ".//a[contains(@class, 'paginator-next')]"
                            )
                            if not btn_next2.is_displayed():
                                logging.info(
                                    f"[ACAO] Fim da paginacao na pagina {pagina + 1}."
                                )
                                break
                            driver.execute_script("arguments[0].click();", btn_next2)
                        except Exception:
                            break

                    if not clicou_opcao:
                        logging.warning(
                            f"[ACAO] Opcao '{escolha}' nao encontrada em nenhuma pagina do lookup."
                        )
                except Exception as e:
                    logging.error(
                        f"[ACAO] Erro ao navegar/clicar na descricao no lookup: {e}"
                    )
            else:
                logging.warning(
                    "[ACAO] Nenhuma opcao valida foi classificada pela IA. O campo ficara em branco para preenchimento manual."
                )

    except Exception as e:
        logging.error(f"[ACAO] Falha ao navegar na aba do processo: {e}")
        try:
            salvar_screenshot(driver, "erro_navegacao_aba_processo")
        except Exception:
            pass

    finally:
        try:
            driver.switch_to.window(original_handle)
            logging.info("[ACAO] Retornou para a aba principal da automacao.")
        except Exception:
            pass
        time.sleep(1)

    return True
