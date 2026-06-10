#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/acoes.py
----------------
Ações automáticas no painel de publicação do Legal One:
  - Abrir dropdown de status
  - Marcar como "Tratado"
  - Marcar como "Sem providências"
"""

import time
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from modules.utils import salvar_screenshot


# ─── Helper de clique seguro ─────────────────────────────────────────────────

def clicar_elemento_seguro(driver, elemento) -> bool:
    """
    Realiza scroll até o elemento e clica. Tenta JS como fallback.

    Returns:
        True se o clique foi bem-sucedido, False caso contrário.
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
        time.sleep(0.5)
        try:
            elemento.click()
        except Exception:
            driver.execute_script("arguments[0].click();", elemento)
        return True
    except Exception as e:
        logging.warning(f"[ACAO] Falha ao clicar no elemento: {e}")
        return False


# ─── Dropdown de status ──────────────────────────────────────────────────────

def abrir_dropdown_status(driver) -> bool:
    """
    Clica no botão de status (ex: 'Pendente') para abrir o menu de ações.
    Tenta XPath (texto visível) e CSS como fallback.

    Returns:
        True se o dropdown foi aberto com sucesso.
    """
    time.sleep(1)

    # Estratégia 1: XPaths pelo texto/atributos
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

    # Estratégia 2: CSS seletores
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
    logging.warning("[ACAO] ⚠️ Não foi possível abrir o dropdown de status.")
    return False


# ─── Clique genérico em opção do menu ────────────────────────────────────────

def _clicar_opcao_menu(driver, texto_alvo: str, nome_acao: str) -> bool:
    """
    Busca e clica em uma opção do menu dropdown pelo texto visível.
    Tenta XPath primeiro, depois JavaScript direto.

    Args:
        texto_alvo: Texto do botão/opção a clicar.
        nome_acao: Nome descritivo para log.
    """
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

    # Fallback: JavaScript
    try:
        result = driver.execute_script(f"""
            var alvo = '{texto_alvo}'.toLowerCase();
            var todos = document.querySelectorAll('a, li, button, span, div');
            for (var i = 0; i < todos.length; i++) {{
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

    salvar_screenshot(driver, f"debug_{nome_acao.lower().replace(' ', '_')}_nao_encontrado")
    logging.warning(f"[ACAO] ⚠️ Opção '{texto_alvo}' não encontrada no menu.")
    return False


# ─── Ações principais ────────────────────────────────────────────────────────

def marcar_tratado(driver) -> bool:
    """
    Abre o dropdown de status e clica em 'Tratado'.

    Returns:
        True se marcado com sucesso.
    """
    try:
        if not abrir_dropdown_status(driver):
            logging.warning("[ACAO] ⚠️ Dropdown não aberto. Não foi possível marcar 'Tratado'.")
            return False

        for texto in ["Tratado", "tratado", "TRATADO"]:
            if _clicar_opcao_menu(driver, texto, "Tratado"):
                logging.info("[ACAO] ✅ Marcado como 'Tratado'.")
                return True

        return False
    except Exception as e:
        logging.warning(f"[ACAO] Falha em marcar_tratado: {e}")
        return False


def marcar_sem_providencia(driver) -> bool:
    """
    Abre o dropdown de status e clica em 'Sem providências'.
    Tenta primeiro pelo botão exato com ícone SVG específico.

    Returns:
        True se marcado com sucesso.
    """
    try:
        if not abrir_dropdown_status(driver):
            logging.warning("[ACAO] ⚠️ Dropdown não aberto. Não foi possível marcar 'Sem providências'.")
            return False

        time.sleep(1)

        # Estratégia prioritária: botão exato com ícone SVG
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
                            logging.info(f"[ACAO] ✅ 'Sem providências' via XPath exato.")
                            time.sleep(2)
                            return True
            except Exception:
                continue

        # Fallback: busca pelo texto
        for texto in ["Sem providências", "Sem providência", "Sem providencia"]:
            if _clicar_opcao_menu(driver, texto, "Sem providências"):
                logging.info("[ACAO] ✅ Marcado como 'Sem providências'.")
                return True

        return False
    except Exception as e:
        logging.warning(f"[ACAO] Falha em marcar_sem_providencia: {e}")
        return False


def obter_classificacao_ia(dados: dict, opcoes: list, adapta_info: dict | None) -> str:
    """
    Envia a publicação e a lista de opções ao expert 'O PROCESSUALISTA v2' do Adapta ONE
    para classificar qual descrição de compromisso é a mais adequada.
    Retorna o texto exato da opção escolhida, ou 'N/A' se não for possível classificar.
    """
    if not adapta_info:
        logging.warning("[ACAO] Adapta ONE não disponível para classificação de descrição. Pulando.")
        return "N/A"

    prompt = (
        f"Com base na publicação jurídica abaixo, identifique qual das seguintes opções de descrição de compromisso "
        f"do escritório é a mais adequada.\n\n"
        f"**PUBLICAÇÃO:**\n{dados.get('conteudo', '')}\n\n"
        f"**OPÇÕES DISPONÍVEIS:**\n"
        + "\n".join(f"- {op}" for op in opcoes) + "\n\n"
        f"Responda APENAS com o texto exato da opção selecionada (copie exatamente como está na lista acima). "
        f"Não adicione introdução, pontuação, explicação ou qualquer texto extra. "
        f"Se nenhuma opção se aplicar, responda exatamente: N/A"
    )

    try:
        client   = adapta_info["client"]
        chat_id  = adapta_info["chat_id"]
        expert_id = adapta_info["expert_id"]

        logging.info("[ACAO] Enviando lista de descrições ao expert do Adapta ONE para classificação...")
        stream = client.send_message_stream(
            chat_id=chat_id,
            text=prompt,
            model_ai="ONE",
            expert_id=expert_id
        )

        full_text = []
        for chunk in stream:
            if isinstance(chunk, dict):
                delta = chunk.get("delta", "") or chunk.get("text", "")
                if delta:
                    full_text.append(delta)

        escolha_raw = "".join(full_text).strip()
        logging.info(f"[ACAO] Expert Adapta ONE respondeu: '{escolha_raw[:200]}...'")

        # Extrai a última linha não-vazia que corresponda a uma opção
        # (o expert às vezes retorna raciocínio interno antes da resposta final)
        linhas = [l.strip() for l in escolha_raw.splitlines() if l.strip()]
        
        # 1. Tenta correspondência exata nas linhas (de baixo para cima)
        for linha in reversed(linhas):
            if linha in opcoes:
                logging.info(f"[ACAO] ✅ Correspondência exata (última linha): '{linha}'")
                return linha
        
        # 2. Correspondência parcial: opção contida em alguma linha
        for linha in reversed(linhas):
            for op in opcoes:
                if op.lower() in linha.lower():
                    logging.info(f"[ACAO] ✅ Correspondência parcial encontrada: '{op}'")
                    return op
        
        # 3. Último recurso: opção contida no texto completo
        for op in opcoes:
            if op.lower() in escolha_raw.lower():
                logging.info(f"[ACAO] ✅ Correspondência no texto completo: '{op}'")
                return op

    except Exception as e:
        logging.error(f"[ACAO] Erro ao classificar descrição no Adapta ONE: {e}")

    return "N/A"


def clicar_link_processo(driver, dados: dict = None, adapta_info: dict = None) -> bool:
    """
    Localiza e clica no link do processo (Processo ou Pasta/Contato)
    dentro do painel de detalhes da publicação.
    Depois, muda para a nova aba aberta, clica em "Compromissos e tarefas",
    "Adicionar" e "Novo compromisso".
    A partir daí:
      - Aguarda o carregamento do formulário (input 'Descricao').
      - Abre o popup de lookup de descrição.
      - Scrapea todas as opções percorrendo a paginação do modal.
      - Envia o texto da publicação e as opções para classificação via IA.
      - Digita a opção selecionada no campo de busca do lookup e clica no item correspondente.
    Por fim, volta para a aba original para que o robô continue.
    """
    logging.info("[ACAO] Tentando clicar no link do processo para abrir em nova aba...")
    
    # Guarda o identificador da aba principal
    original_handle = driver.current_window_handle
    total_abas_antes = len(driver.window_handles)

    # Seletores robustos para os links do processo no cabeçalho de detalhes
    seletores = [
        # Link associado ao texto "Pasta/Contato:"
        (By.XPATH, "//span[contains(text(), 'Pasta/Contato')]/following-sibling::a"),
        # Link associado ao texto "Processo:"
        (By.XPATH, "//span[contains(text(), 'Processo')]/following-sibling::a"),
        # Qualquer link com o formato de link do novajus/legalone para detalhes do processo
        (By.CSS_SELECTOR, "a[href*='/processos/processos/Details/']"),
        (By.CSS_SELECTOR, "a[href*='/processos/details/']"),
    ]
    
    link_clicado = False
    for by, sel in seletores:
        try:
            elementos = driver.find_elements(by, sel)
            for el in elementos:
                if el.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.5)
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    logging.info(f"[ACAO] ✅ Link do processo clicado via seletor: {sel}")
                    link_clicado = True
                    break
            if link_clicado:
                break
        except Exception as e:
            logging.warning(f"[ACAO] Erro ao tentar clicar com seletor {sel}: {e}")
            continue

    if not link_clicado:
        logging.warning("[ACAO] ⚠️ Não foi possível encontrar ou clicar no link do processo.")
        return False

    # Aguarda a nova aba abrir
    try:
        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > total_abas_antes)
        novas_abas = [h for h in driver.window_handles if h != original_handle]
        if novas_abas:
            new_handle = novas_abas[-1]
            # Muda para a nova aba
            driver.switch_to.window(new_handle)
            logging.info("[ACAO] Mudou para a nova aba do processo.")
            time.sleep(5)  # Aguarda carregar a página inicial do processo
            
            # 1. Clica no tab "Compromissos e tarefas"
            wait = WebDriverWait(driver, 15)
            tab_comp = wait.until(EC.element_to_be_clickable((By.ID, "aTab-appointments-and-tasks")))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab_comp)
            time.sleep(0.5)
            try:
                tab_comp.click()
            except Exception:
                driver.execute_script("arguments[0].click();", tab_comp)
            logging.info("[ACAO] ✅ Aba 'Compromissos e tarefas' selecionada.")
            time.sleep(3)

            # 2. Passa o mouse (hover) sobre o botão "Adicionar"
            btn_adicionar = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//span[contains(@class, 'add-popover-menu') and (contains(text(), 'Adicionar') or contains(text(), 'Add'))]")
            ))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn_adicionar)
            time.sleep(0.5)
            
            # Executa hover via JavaScript (mais garantido em ambientes de automação)
            driver.execute_script(
                "var ev1 = new MouseEvent('mouseover', { bubbles: true, cancelable: true, view: window });"
                "var ev2 = new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window });"
                "arguments[0].dispatchEvent(ev1);"
                "arguments[0].dispatchEvent(ev2);",
                btn_adicionar
            )
            
            # Também tenta via ActionChains para mover fisicamente o cursor
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(driver)
                actions.move_to_element(btn_adicionar).perform()
            except Exception:
                pass
                
            logging.info("[ACAO] ✅ Mouse posicionado (hover) sobre o botão 'Adicionar'.")
            time.sleep(1.5)

            # 3. Clica em "Novo compromisso"
            link_clicado = False
            try:
                # Espera curta de 4s para ver se está clicável na tela
                link_novo = WebDriverWait(driver, 4).until(EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(), 'Novo compromisso') or contains(@href, '/processos/compromissos/CreateFromProcesso/')]")
                ))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_novo)
                time.sleep(0.5)
                link_novo.click()
                link_clicado = True
            except Exception:
                logging.info("[ACAO] ⚠️ Click convencional não funcionou, tentando click direto via JavaScript...")
                
            if not link_clicado:
                # Fallback via JavaScript direto no elemento (funciona mesmo se oculto/display:none)
                resultado_js = driver.execute_script("""
                    var links = document.querySelectorAll("a[href*='/processos/compromissos/CreateFromProcesso/']");
                    for (var i = 0; i < links.length; i++) {
                        links[i].scrollIntoView({block: 'center'});
                        links[i].click();
                        return true;
                    }
                    // Alternativa por texto
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
                    link_clicado = True
                
            if link_clicado:
                logging.info("[ACAO] ✅ Link 'Novo compromisso' clicado. Aguardando tela de criação...")
                time.sleep(3)
            else:
                raise Exception("Não foi possível encontrar ou clicar no link 'Novo compromisso'.")

            # 4. Aguarda carregar a página de criação (procurando o input id="Descricao")
            logging.info("[ACAO] Aguardando campo 'Descricao' carregar na tela...")
            input_descricao = wait.until(EC.presence_of_element_located((By.ID, "Descricao")))
            time.sleep(2)  # Pausa extra para renderização completa

            # 5. Clica no botão de lookup de Descrição
            logging.info("[ACAO] Localizando e clicando no botão de lookup para 'Descricao'...")
            xpath_lookup_btn = "//div[contains(@class, 'lookup') and .//input[@id='Descricao']]//div[contains(@class, 'lookup-modal-button')]"
            btn_lookup = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_lookup_btn)))
            try:
                btn_lookup.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_lookup)
            logging.info("[ACAO] ✅ Botão de lookup clicado.")
            time.sleep(2.5)

            # 6. Aguarda o dropdown/tabela de lookup aparecer
            logging.info("[ACAO] Aguardando dropdown/modal de lookup de Descrição...")
            xpath_dropdown = "//div[contains(@id, 'lookup_') and contains(@id, '_dropdown')]"
            dropdown = wait.until(EC.presence_of_element_located((By.XPATH, xpath_dropdown)))

            # 7. Coleta as opções de descrição disponíveis nas páginas do lookup (paginação)
            opcoes = []
            paginas_visitadas = 0
            while paginas_visitadas < 5:  # Limite de segurança de 5 páginas
                rows = dropdown.find_elements(By.XPATH, ".//div[@class='lookup-wrapper']//tr[@data-val-id]")
                for row in rows:
                    try:
                        td = row.find_element(By.XPATH, ".//td[@data-val-field='Value']")
                        texto = td.text.strip()
                        if texto and texto not in opcoes:
                            opcoes.append(texto)
                    except Exception:
                        continue
                
                # Tenta avançar de página
                try:
                    btn_next = dropdown.find_element(By.XPATH, ".//a[contains(@class, 'paginator-next')]")
                    if not btn_next.is_displayed():
                        break
                    try:
                        btn_next.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn_next)
                    time.sleep(1.0)  # Aguarda carregar os itens da nova página
                    paginas_visitadas += 1
                except Exception:
                    break
            
            logging.info(f"[ACAO] ✅ Coletadas {len(opcoes)} opções de descrição para classificação.")

            # 8. Consulta a IA (Adapta ONE ou Groq) para obter qual opção corresponde à publicação
            escolha = "N/A"
            if dados and opcoes:
                escolha = obter_classificacao_ia(dados, opcoes, adapta_info)
                
            logging.info(f"[ACAO] Descrição selecionada pela IA: '{escolha}'")

            # 9. Clica na opção classificada pela IA navegando pelas páginas do lookup (sem usar busca)
            if escolha and escolha != "N/A" and escolha in opcoes:
                try:
                    def _tentar_clicar_linhas(linhas):
                        """Tenta clicar na linha correspondente — exato primeiro, depois parcial."""
                        for row in linhas:
                            try:
                                td = row.find_element(By.XPATH, ".//td[@data-val-field='Value']")
                                texto_td = td.text.strip()
                                if texto_td.lower() == escolha.lower():
                                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
                                    time.sleep(0.4)
                                    try:
                                        row.click()
                                    except Exception:
                                        driver.execute_script("arguments[0].click();", row)
                                    logging.info(f"[ACAO] ✅ Opção selecionada e clicada no lookup: '{escolha}'")
                                    return True
                            except Exception:
                                continue
                        # Correspondência parcial
                        for row in linhas:
                            try:
                                td = row.find_element(By.XPATH, ".//td[@data-val-field='Value']")
                                texto_td = td.text.strip()
                                if escolha.lower() in texto_td.lower() or texto_td.lower() in escolha.lower():
                                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
                                    time.sleep(0.4)
                                    try:
                                        row.click()
                                    except Exception:
                                        driver.execute_script("arguments[0].click();", row)
                                    logging.info(f"[ACAO] ✅ Opção parcial clicada no lookup: '{texto_td}'")
                                    return True
                            except Exception:
                                continue
                        return False

                    # Fecha o lookup atual (pode estar em qualquer página após a coleta)
                    # e reabre para garantir estado limpo na página 1
                    logging.info("[ACAO] Fechando lookup atual e reabrindo para navegar até a opção...")
                    from selenium.webdriver.common.keys import Keys
                    try:
                        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                        time.sleep(1.0)
                    except Exception:
                        pass

                    # Reabre o botão de lookup
                    xpath_lookup_btn2 = "//div[contains(@class, 'lookup') and .//input[@id='Descricao']]//div[contains(@class, 'lookup-modal-button')]"
                    btn_lookup2 = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_lookup_btn2))
                    )
                    try:
                        btn_lookup2.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn_lookup2)
                    logging.info("[ACAO] ✅ Lookup reaberto. Aguardando dropdown...")
                    time.sleep(2.5)

                    # Obtém referência ao novo dropdown
                    xpath_dropdown2 = "//div[contains(@id, 'lookup_') and contains(@id, '_dropdown')]"
                    dropdown2 = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, xpath_dropdown2))
                    )

                    # Navega por todas as páginas procurando a linha correta
                    clicou_opcao = False
                    for pagina in range(6):  # Até 6 páginas de segurança
                        time.sleep(1.0)
                        linhas_pg = dropdown2.find_elements(
                            By.XPATH, ".//div[@class='lookup-wrapper']//tr[@data-val-id]"
                        )
                        clicou_opcao = _tentar_clicar_linhas(linhas_pg)
                        if clicou_opcao:
                            break
                        # Avança de página
                        try:
                            btn_next2 = dropdown2.find_element(
                                By.XPATH, ".//a[contains(@class, 'paginator-next')]"
                            )
                            if not btn_next2.is_displayed():
                                logging.info(f"[ACAO] Fim da paginação na página {pagina + 1}.")
                                break
                            driver.execute_script("arguments[0].click();", btn_next2)
                        except Exception:
                            break

                    if not clicou_opcao:
                        logging.warning(f"[ACAO] ⚠️ Opção '{escolha}' não encontrada em nenhuma página do lookup.")
                except Exception as e:
                    logging.error(f"[ACAO] Erro ao navegar/clicar na descrição no lookup: {e}")
            else:
                logging.warning("[ACAO] ⚠️ Nenhuma opção válida foi classificada pela IA. O campo ficará em branco para preenchimento manual.")

    except Exception as e:
        logging.error(f"[ACAO] ❌ Falha ao navegar na aba do processo: {e}")
        try:
            salvar_screenshot(driver, "erro_navegacao_aba_processo")
        except Exception:
            pass

    finally:
        # Garante que SEMPRE volta para a aba original da lista de publicações
        try:
            driver.switch_to.window(original_handle)
            logging.info("[ACAO] Retornou para a aba principal da automação.")
        except Exception:
            pass
        time.sleep(1)

    return True


