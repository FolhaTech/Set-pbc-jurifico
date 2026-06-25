import logging
import pathlib
import re
import time

from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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
        scrip_path = (
            pathlib.Path(__file__).parent.parent.parent / "scripts" / "all-options.js"
        )
        js_code = scrip_path.read_text(encoding="utf-8")
        driver.execute_script(js_code)

        alvo_lower = texto_alvo.lower()

        print(f"[DEBUG] alvo_lower: {alvo_lower!r}")

        result = driver.execute_script(f"return window.__selectOption({alvo_lower!r});")

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

        if not _clicar_opcao_menu(driver, "Tratada", "Tratada"):
            return False

        time.sleep(2)

        xpath_pendentes = [
            "//a[normalize-space(.)='Pendentes']",
            "//button[normalize-space(.)='Pendentes']",
            "//li[contains(@class,'active')]//a[contains(.,'Pendente')]",
            "//a[contains(@href, 'status=Pendente') or contains(@href, 'status=Pendentes')]",
            "//span[normalize-space(.)='Pendentes']/parent::a",
            "//span[normalize-space(.)='Pendentes']/parent::button",
        ]
        for xp in xpath_pendentes:
            try:
                el = driver.find_element(By.XPATH, xp)
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(2)
                    logging.info(
                        "[ACAO] Marcado como tratado. Aba 'Pendentes' mantida."
                    )
                    return True
            except Exception:
                continue

        logging.info("[ACAO] Marcado como tratado (aba atual nao confirmada).")
        return True
    except Exception as e:
        logging.warning(f"[ACAO] Falha em marcar_tratado: {e}")
        return False


def preencher_data_inicial(driver, data_str: str) -> bool:
    """
    Preenche o campo DtInicial.
    Estrategia: 1) Fechar modal-masks  2) Setar via JS nativo  3) Fallback send_keys
    data_str: no formato 'dd/mm/aaaa' (ex: '03/07/2026').
    """
    if not re.match(r"^\d{2}/\d{2}/\d{4}$", data_str):
        logging.warning(f"[ACAO] Data invalida para DtInicial: '{data_str}'")
        return False

    try:
        wait = WebDriverWait(driver, 10)
        input_dt = wait.until(EC.presence_of_element_located((By.ID, "DtInicial")))

        # ── PASSO 0: Fechar qualquer modal-mask que esteja bloqueando ──
        fechou_modal = driver.execute_script("""
            var masks = document.querySelectorAll('.modal-mask, .modal, .k-overlay');
            var fechou = 0;
            masks.forEach(function(m) {
                if (m.offsetParent !== null && m.style.display !== 'none') {
                    m.click();
                    fechou++;
                }
            });
            document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27, bubbles: true}));
            document.body.dispatchEvent(new KeyboardEvent('keyup', {key: 'Escape', keyCode: 27, bubbles: true}));
            return fechou;
        """)
        if fechou_modal:
            logging.info(
                f"[ACAO] {fechou_modal} modal(s) fechado(s) antes de preencher DtInicial."
            )
            time.sleep(1.0)

        # ── PASSO 1: Scroll + foco ──
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", input_dt
        )
        time.sleep(0.3)
        driver.execute_script("arguments[0].focus();", input_dt)
        time.sleep(0.3)

        # ── PASSO 2: Setar valor via JS nativo (método primário) ──
        sucesso = driver.execute_script(f"""
            var el = document.getElementById('DtInicial');
            if (!el) return 'NO_ELEMENT';

            el.removeAttribute('readonly');
            el.removeAttribute('disabled');

            var data = '{data_str}';
            el.value = data;
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.dispatchEvent(new Event('blur', {{bubbles: true}}));

            // Tentativa adicional via datepicker (nao bloqueante)
            if (window.jQuery && typeof jQuery(el).datepicker === 'function') {{
                try {{
                    var partes = data.split('/');
                    var dataObj = new Date(partes[2], partes[1] - 1, partes[0]);
                    jQuery(el).datepicker('setDate', dataObj);
                    jQuery(el).trigger('change');
                    jQuery(el).trigger('blur');
                }} catch(e) {{}}
            }}

            return 'OK:' + el.value;
        """)
        logging.info(f"[ACAO] JS nativo setDate retorno: {sucesso}")
        time.sleep(0.5)

        # ── PASSO 3: Verificar ──
        valor_final = input_dt.get_attribute("value") or ""
        if data_str in valor_final:
            logging.info(f"[ACAO] Data inicial preenchida com sucesso: '{valor_final}'")
            return True

        # ── PASSO 4: Fallback send_keys (via JS click para bypassar modal-mask) ──
        logging.warning(
            f"[ACAO] JS nativo nao persistiu valor ({valor_final!r}). "
            f"Tentando send_keys como fallback."
        )
        try:
            driver.execute_script("arguments[0].click();", input_dt)
            time.sleep(0.3)
            input_dt.send_keys(Keys.CONTROL, "a")
            time.sleep(0.1)
            input_dt.send_keys(Keys.DELETE)
            time.sleep(0.2)
            for ch in data_str:
                input_dt.send_keys(ch)
                time.sleep(0.08)
            time.sleep(0.5)
            input_dt.send_keys(Keys.TAB)
            time.sleep(0.5)
        except Exception as e:
            logging.warning(f"[ACAO] Fallback send_keys falhou: {e}")

        valor_final = input_dt.get_attribute("value") or ""
        if data_str in valor_final:
            logging.info(
                f"[ACAO] Data inicial preenchida (fallback send_keys): '{valor_final}'"
            )
            return True

        logging.warning(
            f"[ACAO] Nao foi possivel preencher DtInicial. "
            f"Esperado '{data_str}', atual '{valor_final}'."
        )
        salvar_screenshot(driver, "erro_preencher_dt_inicial")
        return False

    except Exception as e:
        logging.warning(f"[ACAO] Falha em preencher_data_inicial: {e}")
        try:
            salvar_screenshot(driver, "erro_preencher_dt_inicial")
        except Exception:
            pass
        return False


def extrair_data_agendamento(resposta_ia: str) -> str | None:
    if not resposta_ia:
        return None
    match = re.search(r"Data do Agendamento:\s*(\d{2}/\d{2}/\d{4})", resposta_ia)
    if match:
        return match.group(1)
    match = re.search(r"(\d{2}/\d{2}/\d{4})", resposta_ia)
    if match:
        return match.group(1)
    return None


def publicacao_sigilosa(dados: dict | None) -> bool:
    if not dados:
        return False

    conteudo = (dados.get("conteudo") or "").lower()

    return (
        "processo sigiloso" in conteudo
        or "consulte os autos digitais" in conteudo
        or "polo p: sigilo" in conteudo
    )


def escolha_fallback_descricao(opcoes: list[str]) -> str:
    prioridades = [
        "Cumprir prazo.",
        "Cumprir prazo",
        "Manifestação",
        "Manifestacao",
    ]

    for prioridade in prioridades:
        for op in opcoes:
            if prioridade.lower() in op.lower():
                return op
    return opcoes[0] if opcoes else "N/A"


def escolher_fallback_tipo(opcoes_tipo: list[str]) -> str:
    prioridades = [
        "Diversos",
        "Atendimento",
        "Outros",
        "Geral",
    ]
    for prioridade in prioridades:
        for op in opcoes_tipo:
            if prioridade.lower() in op.lower():
                return op
    return opcoes_tipo[0] if opcoes_tipo else "N/A"


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
        f"Voce e um assistente juridico especializado em analise de publicacoes processuais.\n"
        f"Com base na publicacao abaixo, identifique qual das opcoes de descricao de compromisso "
        f"e a mais adequada para a equipe executar.\n\n"
        f"**PUBLICACAO:**\n{dados.get('conteudo', '')}\n\n"
        f"**OPCOES DISPONIVEIS:**\n" + "\n".join(f"- {op}" for op in opcoes) + "\n\n"
        f"**REGRAS DE DECISAO (em ordem de importancia):**\n"
        f"1. Identifique o ato processual principal da publicacao (ex: despacho, sentenca, "
        f"intimacao para manifestar, audiencia, julgamento, etc).\n"
        f"2. Escolha a opcao que melhor representa esse ato principal.\n"
        f"3. NAO escolha 'Cumprir prazo' a menos que a publicacao determine literalmente um prazo "
        f"a ser cumprido pela parte (ex: 'intime-se para cumprir o prazo de 5 dias').\n"
        f"4. Se a publicacao for sigilosa, generica ou nao trouxer ato especifico, escolha a opcao "
        f"mais generica (ex: 'Manifestacao', 'Outros', etc), mas NUNCA 'Cumprir prazo' como padrao.\n"
        f"5. Responda N/A somente se a lista de opcoes estiver vazia ou totalmente inutilizavel.\n\n"
        f"**FORMATO DA RESPOSTA:**\n"
        f"Responda APENAS com o texto exato da opcao selecionada (copie exatamente como esta na lista acima). "
        f"Nao adicione introducao, pontuacao, explicacao ou qualquer texto extra."
    )

    try:
        client = adapta_info["client"]

        logging.info(
            "[ACAO] Enviando lista de descricoes ao expert do Adapta ONE para classificacao..."
        )

        escolha_raw = client.enviar_mensagem(prompt).strip()
        logging.info(f"[ACAO] Expert Adapta ONE respondeu: '{escolha_raw[:200]}...'")

        linhas = [l.strip() for l in escolha_raw.splitlines() if l.strip()]

        def _norm(t):
            return re.sub(r"[^a-z0-9\s]", "", t.lower()).strip()

        opcoes_norm = {_norm(op): op for op in opcoes}
        for linha in reversed(linhas):
            n = _norm(linha)
            if n in opcoes_norm:
                op = opcoes_norm[n]
                logging.info(f"[ACAO] Correspondencia exata (ultima linha): '{linha}'")
                return op

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


def obter_classificacao_tipo_ia(
    dados: dict, opcoes: list, adapta_info: dict | None, descricao_escolhida: str
) -> str:
    if not adapta_info:
        logging.warning(
            "[ACAO] Adapta ONE nao disponivel para classificacao de descricao. Pulando."
        )
        return "N/A"

    prompt = (
        f"Com base na publicacao juridica abaixo e na descricao de compromisso ja selecionada, "
        f"identifique qual dos seguintes TIPOS de compromisso e o mais adequado.\n\n"
        f"**DESCRICAO SELECIONADA:** {descricao_escolhida}\n\n"
        f"**PUBLICACAO:**\n{dados.get('conteudo', '')[:1000]}\n\n"
        f"**OPCOES DE TIPO DISPONIVEIS:**\n"
        + "\n".join(f"- {op}" for op in opcoes)
        + "\n\n"
        f"Responda APENAS com o texto exato da opcao selecionada "
        f"(copie exatamente como esta na lista acima). "
        f"Nao adicione introducao, pontuacao, explicacao ou qualquer texto extra. "
        f"Se nenhuma opcao se aplicar, responda exatamente: N/A"
    )

    try:
        client = adapta_info["client"]
        logging.info(
            "[ACAO] Enviando lista de tipos ao expert do Adapta ONE para classificacao..."
        )
        escolha_raw = client.enviar_mensagem(prompt).strip()
        logging.info(f"[ACAO] Expert Adapta ONE respondeu: '{escolha_raw[:200]}...'")

        linhas = [l.strip() for l in escolha_raw.splitlines() if l.strip()]
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
                            "//a[contains(text(), 'Nova tarefa') or contains(@href, '/processos/compromissos/CreateFromProcesso/')]",
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
                scrip_path = (
                    pathlib.Path(__file__).parent.parent.parent
                    / "scripts"
                    / "new-task.js"
                )
                js_code = scrip_path.read_text(encoding="utf-8")
                resultado_js = driver.execute_script(js_code)
                if resultado_js:
                    link_clicado_comp = True

            if link_clicado_comp:
                logging.info(
                    "[ACAO] Link 'Novo Tarefa' clicado. Aguardando tela de criacao..."
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
            opcoes_map = {}  # texto -> data-val-id (para setar via JS depois)
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
                        val_id = row.get_attribute("data-val-id") or ""
                        if texto and texto not in opcoes:
                            opcoes.append(texto)
                            opcoes_map[texto] = val_id
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

        opcoes_tipo_pre = []
        opcoes_tipo_map_pre = {}
        try:
            logging.info("[ACAO] Pre-buscando opcoes de Tipo via XHR...")
            html_tipo = driver.execute_script("""
                        try {
                            var xhr = new XMLHttpRequest();
                            xhr.open('GET', '/config/TipoAndamentoCompromissoTarefa/LookupTreeTiposCompromisso', false);
                            xhr.send();
                            return xhr.responseText;
                        } catch(e) {
                            return 'XHR_ERR:' + e.message;
                        }
                    """)
            if html_tipo and not html_tipo.startswith("XHR_ERR:"):
                import json as _json

                try:
                    data_tipo = _json.loads(html_tipo)
                    rows_tipo = data_tipo.get("Rows", [])
                    for row in rows_tipo:
                        value = (row.get("Value") or "").strip()
                        rid = row.get("Id") or ""
                        if value and value not in opcoes_tipo_pre:
                            opcoes_tipo_pre.append(value)
                            opcoes_tipo_map_pre[value] = rid
                    logging.info(
                        f"[ACAO] Pre-busca Tipo: {len(opcoes_tipo_pre)} opcoes via XHR. "
                        f"Amostra: {opcoes_tipo_pre[:10]}"
                    )
                except Exception as e:
                    logging.warning(
                        f"[ACAO] Erro ao parsear XHR de Tipo na pre-busca: {e}"
                    )
        except Exception as e:
            logging.warning(f"[ACAO] Pre-busca de Tipo via XHR falhou: {e}")

        escolha = "N/A"
        if dados and opcoes:
            if publicacao_sigilosa(dados):
                escolha = escolha_fallback_descricao(opcoes)
                logging.info(
                    f"[ACAO] Publicacao sigilosa/generica. Usando fallback de descricao: '{escolha}'"
                )
            else:
                escolha = obter_classificacao_ia(dados, opcoes, adapta_info)

                if not escolha or escolha == "N/A":
                    escolha = escolha_fallback_descricao(opcoes)
                    logging.info(
                        f"[ACAO] Nao foi possivel classificar via IA. Usando fallback de descricao: '{escolha}'"
                    )

        logging.info(f"[ACAO] Escolha de descricao: '{escolha}'")

        if escolha and escolha != "N/A":
            val_id = opcoes_map.get(escolha, "")
            # Se não encontrou por exatidão, tenta correspondência parcial
            if not val_id:
                for texto, vid in opcoes_map.items():
                    if (
                        escolha.lower() in texto.lower()
                        or texto.lower() in escolha.lower()
                    ):
                        val_id = vid
                        escolha = texto  # usa o texto exato da lista
                        break

            if val_id:
                logging.info(
                    f"[ACAO] Setando Descricao via JS: texto='{escolha}' id='{val_id}'"
                )
                texto_escapado = escolha.replace("'", "\\'").replace('"', '\\"')
                driver.execute_script(f"""
                    var descInput = document.getElementById('Descricao');
                    var descId = document.getElementById('DescricaoId');
                    if (descInput) {{
                        descInput.value = '{texto_escapado}';
                        descInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                        descInput.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                    if (descId) {{
                        descId.value = '{val_id}';
                        descId.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                    var hidden = document.querySelector('input[data-val-control="lookup"][data-val-field="Value"]');
                    if (hidden && hidden.id !== 'Descricao') {{
                        hidden.value = '{val_id}';
                        hidden.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                """)
                time.sleep(1)
                try:
                    input_desc = driver.find_element(By.ID, "Descricao")
                    valor = input_desc.get_attribute("value") or ""
                    if escolha.lower() in valor.lower():
                        logging.info(f"[ACAO] Descricao confirmada via JS: '{escolha}'")
                    else:
                        logging.warning(
                            f"[ACAO] JS nao colou Descricao. Esperado '{escolha}', atual '{valor}'."
                        )
                except Exception:
                    logging.warning(
                        "[ACAO] Nao foi possivel verificar Descricao apos JS."
                    )
            else:
                logging.warning(
                    f"[ACAO] Nao foi possivel encontrar data-val-id para '{escolha}'. "
                    f"Tentando abrir lookup como fallback..."
                )
                try:
                    btn_lookup = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_lookup_btn))
                    )
                    btn_lookup.click()
                    time.sleep(2.5)
                    dropdown = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, xpath_dropdown))
                    )
                    driver.execute_script(
                        "arguments[0].querySelector('.pagination-first a, .paginator-first a').click();",
                        dropdown,
                    )
                    time.sleep(0.5)
                    clicou = False
                    for pagina in range(6):
                        rows = dropdown.find_elements(
                            By.XPATH,
                            ".//div[@class='lookup-wrapper']//tr[@data-val-id]",
                        )
                        for row in rows:
                            try:
                                td = row.find_element(
                                    By.XPATH, ".//td[@data-val-field='Value']"
                                )
                                texto = td.text.strip()
                                if (
                                    escolha.lower() in texto.lower()
                                    or texto.lower() in escolha.lower()
                                ):
                                    driver.execute_script(
                                        "arguments[0].scrollIntoView({block:'center'});",
                                        row,
                                    )
                                    time.sleep(0.3)
                                    try:
                                        row.click()
                                    except Exception:
                                        driver.execute_script(
                                            "arguments[0].click();", row
                                        )
                                    logging.info(
                                        f"[ACAO] Descricao (fallback) selecionada: '{texto}'"
                                    )
                                    clicou = True
                                    break
                            except Exception:
                                continue
                        if clicou:
                            break
                        try:
                            btn_next = dropdown.find_element(
                                By.XPATH, ".//a[contains(@class, 'paginator-next')]"
                            )
                            if not btn_next.is_displayed():
                                break
                            driver.execute_script("arguments[0].click();", btn_next)
                            time.sleep(1.0)
                        except Exception:
                            break
                    if not clicou:
                        logging.warning(
                            "[ACAO] Fallback de lookup tambem nao encontrou a descricao."
                        )
                except Exception:
                    logging.warning("[ACAO] Fallback de lookup tambem falhou.")
        else:
            logging.info("[ACAO] Nao foi possivel classificar a descricao.")

        if escolha and escolha != "N/A":
            opcoes_tipo = []
            opcoes_tipo_map = {}  # Value -> Id (para setar depois)

            # ESTRATÉGIA 1: Usar dados já pré-buscados via XHR
            if opcoes_tipo_pre:
                opcoes_tipo = opcoes_tipo_pre
                opcoes_tipo_map = opcoes_tipo_map_pre
                logging.info(
                    f"[ACAO] Usando {len(opcoes_tipo)} opcoes de Tipo da pre-busca."
                )
            else:
                # Fallback: buscar via XHR agora
                try:
                    logging.info(
                        "[ACAO] Buscando dados da arvore via XHR (fallback)..."
                    )
                    html_arvore = driver.execute_script("""
                                    try {
                                        var xhr = new XMLHttpRequest();
                                        xhr.open('GET', '/config/TipoAndamentoCompromissoTarefa/LookupTreeTiposCompromisso', false);
                                        xhr.send();
                                        return xhr.responseText;
                                    } catch(e) {
                                        return 'XHR_ERR:' + e.message;
                                    }
                                """)
                    if html_arvore and not html_arvore.startswith("XHR_ERR:"):
                        import json

                        try:
                            data = json.loads(html_arvore)
                            rows = data.get("Rows", [])
                            for row in rows:
                                value = (row.get("Value") or "").strip()
                                rid = row.get("Id") or ""
                                if value and value not in opcoes_tipo:
                                    opcoes_tipo.append(value)
                                    opcoes_tipo_map[value] = rid
                            logging.info(
                                f"[ACAO] Fallback XHR: {len(opcoes_tipo)} opcoes de Tipo."
                            )
                        except json.JSONDecodeError as je:
                            logging.warning(f"[ACAO] JSON invalido no XHR: {je}")
                except Exception as e:
                    logging.warning(f"[ACAO] Erro na estrategia XHR: {e}")

                # ESTRATÉGIA 2: fallback DOM (se XHR também falhou)
                if not opcoes_tipo:
                    try:
                        opcoes_js = driver.execute_script("""
                                        var resultados = [];
                                        var containers = document.querySelectorAll(
                                            '.lookup-tree-container, .k-popup, .k-animation-container, ' +
                                            '[data-role="treeview"], div[class*="tree"], ' +
                                            '.modal:not(.modal-mask), .modal-content, .modal-body'
                                        );
                                        if (containers.length === 0) { containers = [document.body]; }
                                        containers.forEach(function(container) {
                                            if (container !== document.body && container.offsetParent === null) return;
                                            var elementos = container.querySelectorAll('span, li, .k-in, .k-item, a.k-link, [data-uid], div[role="treeitem"]');
                                            elementos.forEach(function(el) {
                                                if (el.offsetParent === null) return;
                                                var txt = (el.innerText || el.textContent || '').trim();
                                                if (txt && txt.length > 3 && txt.length < 150 && !txt.includes('\\n') && resultados.indexOf(txt) === -1) {
                                                    resultados.push(txt);
                                                }
                                            });
                                        });
                                        return resultados;
                                    """)
                        if opcoes_js:
                            opcoes_tipo = [t for t in opcoes_js if len(t) > 3]
                    except Exception as e2:
                        logging.warning(f"[ACAO] Erro na estrategia DOM: {e2}")

            logging.info(f"[ACAO] {len(opcoes_tipo)} opcoes de Tipo extraidas.")

            # ── IA Classification ──
            escolha_tipo = "N/A"
            if dados and opcoes_tipo:
                escolha_tipo = obter_classificacao_tipo_ia(
                    dados, opcoes_tipo, adapta_info, escolha
                )
            logging.info(f"[ACAO] IA escolheu Tipo: '{escolha_tipo}'")

            if (not escolha_tipo or escolha_tipo == "N/A") and opcoes_tipo:
                escolha_tipo = escolher_fallback_tipo(opcoes_tipo)
                logging.info(f"[ACAO] Usando fallback de Tipo: '{escolha_tipo}'")

            if escolha_tipo and escolha_tipo != "N/A":
                # Setar via JS usando o ID do JSON (evita reabrir popup)
                tipo_id = opcoes_tipo_map.get(escolha_tipo, "")
                if not tipo_id:
                    for texto, tid in opcoes_tipo_map.items():
                        if (
                            escolha_tipo.lower() in texto.lower()
                            or texto.lower() in escolha_tipo.lower()
                        ):
                            tipo_id = tid
                            escolha_tipo = texto
                            break

                texto_escapado = escolha_tipo.replace("'", "\\'")
                driver.execute_script(f"""
                    var tt = document.getElementById('TipoText');
                    var ti = document.getElementById('TipoId');
                    if (tt) {{
                        tt.value = '{texto_escapado}';
                        tt.dispatchEvent(new Event('input', {{bubbles:true}}));
                        tt.dispatchEvent(new Event('change', {{bubbles:true}}));
                    }}
                    if (ti) {{
                        ti.value = '{tipo_id}';
                        ti.dispatchEvent(new Event('change', {{bubbles:true}}));
                    }}
                """)
                logging.info(
                    f"[ACAO] Tipo setado via JS: texto='{escolha_tipo}' id='{tipo_id}'"
                )
                time.sleep(1)
            else:
                driver.execute_script("""
                    var tt = document.getElementById('TipoText');
                    if (tt && !tt.value) {
                        tt.value = 'Diversos';
                        tt.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                """)
                logging.info("[ACAO] Tipo nao classificado. Restaurado 'Diversos'.")

            # ── Confirmar Tipo ──
            time.sleep(2)
            try:
                input_tipo = driver.find_element(By.ID, "TipoText")
                valor = input_tipo.get_attribute("value") or ""
                if valor.strip():
                    logging.info(f"[ACAO] CONFIRMADO! Campo Tipo: '{valor}'")
                else:
                    logging.warning("[ACAO] Campo Tipo continua vazio.")
            except Exception as e:
                logging.warning(f"[ACAO] Erro ao confirmar Tipo: {e}")

            # ── Preencher DtInicial (Início previsto/efetivo) ──
        data_inicial = None
        # 1) Fonte preferencial: data_agendamento vinda do use case
        if dados and dados.get("data_agendamento"):
            data_inicial = dados["data_agendamento"]
            logging.info(
                f"[ACAO] Data de agendamento recebida do use case: '{data_inicial}'"
            )
        # 2) Fallback: extrair do texto da IA
        elif dados and dados.get("resumo_ia"):
            data_inicial = extrair_data_agendamento(dados["resumo_ia"])
            if data_inicial:
                logging.info(
                    f"[ACAO] Data extraida da resposta da IA: '{data_inicial}'"
                )

        if data_inicial:
            # Converter date -> dd/mm/aaaa se necessário
            if hasattr(data_inicial, "strftime"):
                data_str = data_inicial.strftime("%d/%m/%Y")
            else:
                data_str = str(data_inicial)
            time.sleep(1)
            if not preencher_data_inicial(driver, data_str):
                logging.warning("[ACAO] Falha ao preencher DtInicial.")
        else:
            logging.info("[ACAO] Pulando DtInicial - nenhuma data disponivel.")

        data_publicacao_str = None
        if dados:
            dp = dados.get("data_disponibilizacao", "N/A")
            if dp and dp != "N/A":
                data_publicacao_str = dp
                logging.info(
                    f"[ACAO] Data de disponibilizacao: '{data_publicacao_str}'"
                )

        if data_publicacao_str:
            time.sleep(0.5)
            try:
                driver.execute_script(f"""
                            var el = document.getElementById('DtPublicacao');
                            if (el) {{
                                el.removeAttribute('readonly');
                                el.removeAttribute('disabled');
                                el.value = '{data_publicacao_str}';
                                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                                el.dispatchEvent(new Event('blur', {{bubbles: true}}));
                                if (window.jQuery && typeof jQuery(el).datepicker === 'function') {{
                                    try {{
                                        var partes = '{data_publicacao_str}'.split('/');
                                        var dataObj = new Date(partes[2], partes[1] - 1, partes[0]);
                                        jQuery(el).datepicker('setDate', dataObj);
                                    }} catch(e) {{}}
                                }}
                                return 'OK:' + el.value;
                            }}
                            return 'NO_ELEMENT';
                            """)
                logging.info(f"[ACAO] DtPublicacao preenchido: '{data_publicacao_str}'")
            except Exception as e:
                logging.warning(f"[ACAO] Falha ao preencher DtPublicacao: {e}")
        else:
            logging.info("[ACAO] Pulando DtPublicacao - data indisponivel.")

        logging.info("[ACAO] Clicando em 'Salvar e Fechar'...")
        time.sleep(1)
        try:
            btn_salvar = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//button[@name='ButtonSave' and contains(normalize-space(.), 'Salvar')]",
                    )
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", btn_salvar
            )
            time.sleep(0.3)
            try:
                btn_salvar.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_salvar)
            logging.info("[ACAO] Botao 'Salvar e fechar' clicado.")
            time.sleep(3)
        except Exception as e:
            logging.warning(f"[ACAO] Erro ao clicar em 'Salvar e Fechar': {e}")
            try:
                driver.execute_script("""
                                var btns = document.querySelectorAll('button[type="submit"]');
                                for (var i = 0; i < btns.length; i++) {
                                    var txt = (btns[i].innerText || '').trim();
                                    if (txt.indexOf('Salvar') >= 0) {
                                        btns[i].scrollIntoView({block:'center'});
                                        btns[i].click();
                                        return txt;
                                    }
                                }
                                return null;
                            """)
                logging.info("[ACAO] 'Salvar e fechar' clicado via JS fallback.")
                time.sleep(3)
            except Exception:
                logging.warning("[ACAO] Fallback 'Salvar e fechar' tambem falhou.")

    except Exception as e:
        logging.error(f"[ACAO] Falha ao navegar na aba do processo: {e}")
        try:
            salvar_screenshot(driver, "erro_navegacao_aba_processo")
        except Exception:
            pass

    finally:
        try:
            try:
                if len(driver.window_handles) > 1:
                    abas = [h for h in driver.window_handles if h != original_handle]
                    if abas:
                        driver.switch_to.window(abas[0])
                    driver.close()
            except Exception as e:
                logging.error(f"[ACAO] Falha ao fechar aba do processo: {e}")
                pass

            driver.switch_to.window(original_handle)
            logging.info("[ACAO] Aba do processo fechada com sucesso.")
        except Exception as e:
            logging.error(f"[ACAO] Falha ao fechar aba do processo: {e}")
            pass
        time.sleep(1)

        try:
            logging.info("[ACAO] Marcar publicacoes como tratadas ...")
            if marcar_tratado(driver):
                logging.info("[ACAO] Publicacoes marcadas como tratadas com sucesso.")
            else:
                logging.warning("[ACAO] Falha ao marcar publicacoes como tratadas.")
        except Exception as e:
            logging.error(f"[ACAO] Falha ao marcar publicacoes como tratadas: {e}")
            pass
    return True
