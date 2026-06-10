#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — Ponto de entrada único da automação jurídica (Adapta ONE)
==================================================================

Uso:
  python run.py                      → Processa a primeira publicação e envia ao Adapta ONE (padrão)
  python run.py --todas              → Processa TODAS as publicações e envia ao Adapta ONE
  python run.py --sem-adapta         → Processa apenas no modo offline (sem IA)
  python run.py --todas --sem-adapta → Processa todas em modo offline (sem IA)

Fluxo padrão:
  1. Login no Legal One (Thomson Reuters)
  2. Acessa seção de Publicações
  3. Aplica filtros (60 dias + responsável)
  4. Raspa dados
  5. Cruza dados do autor com a planilha Excel do escritório
  6. Analisa a publicação com o expert "O PROCESSUALISTA v2" no Adapta ONE
  7. Marca status no sistema (Sem providências se for da operadora/polo passivo)
  8. Gera relatório JSON consolidado
"""

import sys
import time
import logging
import argparse
import uuid
import re
from datetime import datetime

# ── Módulos da automação ──────────────────────────────────────────────────────
from modules.utils       import configurar_logging, salvar_screenshot, diagnosticar_pagina, salvar_em_json, calcular_datas_agendamento
from modules.driver      import configurar_driver
from modules.login       import login_thomson_reuters
from modules.navegacao   import (
    acessar_publicacoes,
    selecionar_periodo_60_dias,
    abrir_mais_filtros,
    selecionar_responsavel,
    aplicar_filtros,
)
from modules.scraper     import raspar_detalhes_publicacao
from modules.acoes       import marcar_tratado, marcar_sem_providencia, clicar_link_processo
from modules.relatorio   import gerar_json_relatorio
from config.settings     import MAX_PUBLICACOES, RPM_DELAY, RESPONSAVEL_ALVO, ARQUIVO_JSON

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException

# Importa Adapta ONE
from modules.agente_adapta_one import (
    auto_extract_clerk_token,
    check_jwt_expired,
    renew_local_token,
    verificar_cliente_planilha,
    AdaptaOneClient,
    _localizar_expert
)

# Força UTF-8 no console Windows (para emojis)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ─── Pipelines ───────────────────────────────────────────────────────────────

def _processar_publicacao(driver, dados: dict, adapta_info: dict | None) -> dict:
    """
    Executa a verificação de polo na planilha, análise no Adapta ONE e toma
    a ação correspondente no sistema.
    """
    processo = dados.get("processo_numero", "N/A")
    logging.info(f"[PIPELINE] Analisando processo: {processo}")

    # 1. Identificar polo ativo (autor)
    campos = dados.get("conteudo_parsed", {}).get("campos", {})
    autor = campos.get("polo_a", "") or "N/A"
    
    # 2. Verificar na planilha Excel se é nosso cliente
    logging.info(f"[PIPELINE] Cruzando '{autor}' com a planilha base...")
    resultado_planilha = verificar_cliente_planilha(autor, processo)
    e_nosso = resultado_planilha["e_nosso"]
    lado = "nosso_cliente" if e_nosso else "operadora"
    
    dados["lado_processo"] = lado
    dados["sem_providencia"] = not e_nosso
    decisao_str = "AGENDAR" if e_nosso else "SEM PROVIDÊNCIA"
    classificacao_label = "✅ Nosso Cliente" if e_nosso else "⚪ Sem Providência (Operadora)"
    
    # Obter data de disponibilização
    data_disp = dados.get("data_disponibilizacao") or "N/A"
    if not data_disp or data_disp == "N/A":
        data_disp = datetime.now().strftime("%d/%m/%Y")

    # Estimativa de prazo inicial
    prazo_dias = 5 if "despacho" in dados.get("tipo", "").lower() else 15
    agendamento_info = calcular_datas_agendamento(prazo_dias, data_disp)
    data_agendamento_sugerida = agendamento_info['data_agendamento'] if agendamento_info else "N/A"

    # Monta partes
    reu_raw = campos.get("polo_p", "")
    reu = (", ".join(reu_raw) if isinstance(reu_raw, list) else reu_raw) or "N/A"

    # 3. Análise IA com o expert do Adapta ONE (se ativo e disponível)
    resposta_expert = None
    if adapta_info:
        advogados_parsed = dados.get("advogados", [])
        advs_str = "; ".join(
            f"{a.get('nome','?')} (OAB {a.get('oab','?')})"
            for a in advogados_parsed
        ) if advogados_parsed else "N/A"

        instrucao_lado = (
            "Esta publicação é do **nosso cliente** como polo ativo. "
            "Analise o que foi determinado e indique claramente a data estipulada pelo juiz (se houver) e a ação que nossa equipe deve tomar."
            if e_nosso else
            "Esta publicação é relativa à **parte contrária (operadora)**. "
            "Analise o conteúdo normalmente, mas indique ao final que nenhuma ação ativa é necessária da nossa parte."
        )

        prompt = (
            f"Você é um assistente jurídico objetivo. Analise esta publicação processual de forma CONCISA.\n\n"
            f"**DADOS DA PUBLICAÇÃO:**\n"
            f"- **Data de Disponibilização:** {data_disp}\n"
            f"- **Número Único:** {campos.get('numero_unico', processo)}\n"
            f"- **Polo A (Ativo):** {campos.get('polo_a', autor)}\n"
            f"- **Polo P (Passivo):** {reu}\n"
            f"- **Advogados:** {advs_str}\n"
            f"- **Classificação:** {classificacao_label}\n\n"
            f"**CONTEÚDO DA PUBLICAÇÃO:**\n{dados.get('conteudo', '')}\n\n"
            f"---\n\n"
            f"**INSTRUÇÕES:**\n"
            f"1. Leia o conteúdo acima e **identifique o prazo dado pelo juiz** (em dias).\n"
            f"2. Com base na **Data de Disponibilização ({data_disp})** e no prazo identificado, calcule:\n"
            f"   - **Data Limite** = Data de Disponibilização + prazo do juiz\n"
            f"   - **Data de Agendamento** = Data Limite - 5 dias (sempre 5 dias antes do prazo)\n"
            f"3. {instrucao_lado}\n"
            f"4. Responda SOMENTE com a tabela abaixo preenchida + o resumo de agendamento destacado + 1 parágrafo curto (máximo 3 frases) detalhando a ação recomendada.\n"
            f"5. NÃO escreva introduções, saudações ou comentários extras.\n\n"
            f"**TABELA DE RESPOSTA (preencha os campos entre colchetes):**\n\n"
            f"| Campo | Valor |\n"
            f"| --- | --- |\n"
            f"| **Processo nº** | {processo} |\n"
            f"| **Classificação** | {classificacao_label} |\n"
            f"| **Data de Disponibilização** | {data_disp} |\n"
            f"| **Polo Ativo** | {campos.get('polo_a', autor)} |\n"
            f"| **Polo Passivo** | {reu} |\n"
            f"| **Prazo Identificado (juiz)** | [X dias] |\n"
            f"| **📅 Data Limite (Prazo Final)** | [DD/MM/AAAA] |\n"
            f"| **📅 Data de Agendamento (-5 dias)** | [DD/MM/AAAA] |\n"
            f"| **Ação Necessária** | {'✅ SIM — detalhar abaixo' if e_nosso else '⚪ NÃO — publicação da operadora'} |\n\n"
            f"**RESUMO DE AGENDAMENTO (PREENCHA E DESTAQUE ESTE BLOCO AO FINAL DE FORMA ISOLADA):**\n"
            f"- **Decisão:** {decisao_str}\n"
            f"- **Data do Agendamento:** {data_agendamento_sugerida}\n"
        )

        logging.info("[PIPELINE] Enviando dados ao expert do Adapta ONE...")
        full_text = []
        try:
            stream = adapta_info["client"].send_message_stream(
                chat_id=adapta_info["chat_id"],
                text=prompt,
                model_ai="ONE",
                expert_id=adapta_info["expert_id"]
            )
            print("💬 [O PROCESSUALISTA v2]: ", end="", flush=True)
            for chunk in stream:
                if isinstance(chunk, dict):
                    if chunk.get("type") == "reasoning-delta":
                        continue
                    delta = chunk.get("delta", "") or chunk.get("text", "")
                    if delta:
                        print(delta, end="", flush=True)
                        full_text.append(delta)
            print()
            resposta_expert = "".join(full_text)
            dados["analise_processualista"] = resposta_expert

            # Extrai prazo e data de agendamento do retorno da IA
            data_ia = re.search(r'Data d[o|e] Agendamento[^\d]*(\d{2}/\d{2}/\d{4})', resposta_expert, re.IGNORECASE)
            data_agendada_final = data_ia.group(1) if data_ia else data_agendamento_sugerida

            prazo_ia = re.search(r'Prazo Identificado \(juiz\)[^\d]*(\d+)', resposta_expert, re.IGNORECASE)
            if prazo_ia:
                prazo_dias = int(prazo_ia.group(1))

            agend = calcular_datas_agendamento(prazo_dias, data_disp)
            if agend:
                agend["data_agendamento"] = data_agendada_final
                dados["agendamento"] = agend

            dados["data_agendada"] = data_agendada_final
            dados["decisao_agendamento"] = decisao_str

        except Exception as e:
            logging.error(f"[PIPELINE] Falha ao consultar o Adapta ONE: {e}")

    # Fallback se não usar Adapta ONE ou em caso de falha
    if not resposta_expert:
        dados["analise_processualista"] = None
        dados["data_agendada"] = data_agendamento_sugerida
        dados["decisao_agendamento"] = decisao_str
        dados["agendamento"] = agendamento_info

    # Preenche analise_gemini para retrocompatibilidade com o relatório
    dados["analise_gemini"] = {
        "resumo": resposta_expert[:300] + "..." if resposta_expert else "Análise offline baseada na planilha.",
        "lado_processo": lado,
        "urgencia": "ALTA" if (dados.get("agendamento") and dados["agendamento"].get("status_temporal") in ("URGENTE", "ATRASADO")) else "MEDIA",
        "prazo_recomendado_dias_uteis": prazo_dias,
        "acao_recomendada": "Revisar análise processual." if e_nosso else "Sem providências necessárias.",
        "requer_acao": e_nosso,
        "polo_a": autor,
        "polo_p": reu,
    }

    # Imprime resumo
    data_str = dados.get("data_agendada") or "N/A"
    print(f"\n{'🌟' * 30}")
    print(f"📢 [RESUMO]  Processo: {dados.get('processo_numero')}")
    print(f"   ⚖️  Decisão: {decisao_str}  |  📅 Agendamento: {data_str}")
    print(f"{'🌟' * 30}\n")

    # 4. Executar ações no sistema Thomson Reuters
    if lado == "operadora":
        sucesso = marcar_sem_providencia(driver)
        dados["acao_executada"]  = "Sem providencia" if sucesso else "Falha ao marcar"
        dados["status_decidido"] = dados["acao_executada"]
        if sucesso:
            logging.info(f"[PIPELINE] ✅ '{dados['processo_numero']}' → Sem providência")
        else:
            logging.error(f"[PIPELINE] ❌ Falha ao marcar Sem providências")

    elif lado == "nosso_cliente":
        dados["acao_executada"]  = "Pendente revisao manual"
        dados["status_decidido"] = "Pendente"
        logging.info(f"[PIPELINE] ⏳ '{dados['processo_numero']}' → Pendente (revisão manual)")
        clicar_link_processo(driver, dados, adapta_info)

    return dados


def pipeline_primeira_publicacao(driver, adapta_info: dict | None) -> int:
    """
    Processa apenas a PRIMEIRA publicação visível na lista.
    """
    try:
        logging.info("[PIPELINE] Aguardando lista de publicações...")
        items = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[id^='publication-item-']"))
        )

        if not items:
            logging.warning("[PIPELINE] Nenhuma publicação encontrada na lista.")
            return 0

        primeiro = items[0]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", primeiro)
        primeiro.click()
        time.sleep(3)

        dados = raspar_detalhes_publicacao(driver)
        dados = _processar_publicacao(driver, dados, adapta_info)
        salvar_em_json(dados)
        logging.info("[PIPELINE] ✅ Primeira publicação processada.")
        return 1

    except Exception as e:
        logging.error(f"[PIPELINE] Erro na primeira publicação: {e}")
        salvar_screenshot(driver, "erro_primeira_publicacao")
        return 0


def pipeline_todas_publicacoes(driver, adapta_info: dict | None, max_pubs: int = MAX_PUBLICACOES) -> int:
    """
    Processa TODAS as publicações da lista sequencialmente até max_pubs.
    """
    processados = 0
    ids_processados = set()

    while processados < max_pubs:
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[id^='publication-item-']"))
            )
            itens = driver.find_elements(By.CSS_SELECTOR, "div[id^='publication-item-']")

            proximo, proximo_id = None, None
            for item in itens:
                try:
                    item_id = item.get_attribute("id")
                    if item_id and item_id not in ids_processados:
                        proximo = item
                        proximo_id = item_id
                        break
                except StaleElementReferenceException:
                    continue

            if not proximo:
                logging.info(f"[PIPELINE] Lista esgotada após {processados} publicações.")
                break

            ids_processados.add(proximo_id)
            logging.info(f"[PIPELINE] Iteração {processados + 1}/{max_pubs} — id: {proximo_id}")

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", proximo)
            time.sleep(0.8)

            try:
                proximo.click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                driver.execute_script("arguments[0].click();", proximo)

            time.sleep(3)

            dados = raspar_detalhes_publicacao(driver)
            dados = _processar_publicacao(driver, dados, adapta_info)
            salvar_em_json(dados)
            processados += 1
            time.sleep(RPM_DELAY)

        except Exception as e:
            logging.error(f"[PIPELINE] Erro na iteração {processados + 1}: {e}")
            salvar_screenshot(driver, f"erro_iteracao_{processados + 1}")
            processados += 1
            time.sleep(2)

    return processados


# ─── Função principal ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Automação de Publicações Jurídicas — Legal One"
    )
    parser.add_argument(
        "--todas",
        action="store_true",
        help="Processa todas as publicações (padrão: apenas a primeira)"
    )
    parser.add_argument(
        "--sem-adapta",
        action="store_true",
        help="Desativa o envio de publicações ao Adapta ONE (ativo por padrão)"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=MAX_PUBLICACOES,
        help=f"Número máximo de publicações a processar (padrão: {MAX_PUBLICACOES})"
    )
    args = parser.parse_args()
    args.adapta = not args.sem_adapta

    # Logging
    configurar_logging()

    # Banner
    print("\n" + "=" * 70)
    print("⚖️   AUTOMAÇÃO DE PUBLICAÇÕES JURÍDICAS — Legal One")
    print(f"     Modo: {'Todas as publicações' if args.todas else 'Primeira publicação'}")
    if args.adapta:
        print("     + Análise Adapta ONE (O PROCESSUALISTA v2) ativa")
    else:
        print("     + Modo Offline (apenas planilha)")
    print("=" * 70 + "\n")

    # Inicializa Adapta ONE (se aplicável)
    adapta_info = None
    if args.adapta:
        logging.info("[MAIN] Inicializando Cliente Adapta ONE...")
        token = auto_extract_clerk_token()
        if not token or check_jwt_expired(token):
            token = renew_local_token() or token
        if not token:
            logging.error("[MAIN] ❌ Token do Adapta ONE não obtido. Certifique-se de que o desktop está aberto.")
            sys.exit(1)

        client = AdaptaOneClient(token)
        expert_id = _localizar_expert(client)
        if not expert_id:
            logging.error("[MAIN] ❌ Expert 'O PROCESSUALISTA v2' não encontrado.")
            sys.exit(1)

        chat_id = None
        try:
            chats = client.list_chats()
            chats_list = chats.get("data", []) if isinstance(chats, dict) else chats
            if chats_list:
                chat_id = chats_list[0].get("id")
        except Exception:
            pass
        if not chat_id:
            chat_id = str(uuid.uuid4())

        adapta_info = {
            "client": client,
            "expert_id": expert_id,
            "chat_id": chat_id
        }
        logging.info("[MAIN] ✅ Cliente Adapta ONE e Expert conectados com sucesso.")

    driver = None
    try:
        # ── 1. Iniciar driver ────────────────────────────────────────────────
        driver = configurar_driver(usar_undetected=True)

        # ── 2. Login ─────────────────────────────────────────────────────────
        login_thomson_reuters(driver)
        logging.info("[MAIN] Aguardando 10s para SPA estabilizar...")
        time.sleep(10)
        diagnosticar_pagina(driver, "pos_login")

        # ── 3. Navegação ─────────────────────────────────────────────────────
        acessar_publicacoes(driver)
        time.sleep(3)
        diagnosticar_pagina(driver, "pos_publicacoes")

        # ── 4. Filtros ───────────────────────────────────────────────────────
        selecionar_periodo_60_dias(driver)
        time.sleep(2)
        abrir_mais_filtros(driver)
        time.sleep(3)
        selecionar_responsavel(driver, RESPONSAVEL_ALVO)
        time.sleep(1)
        aplicar_filtros(driver)
        time.sleep(3)

        # ── 5. Pipeline de processamento ─────────────────────────────────────
        if args.todas:
            total = pipeline_todas_publicacoes(driver, adapta_info, max_pubs=args.max)
            logging.info(f"[MAIN] ✅ Pipeline concluído — {total} publicações processadas.")
        else:
            pipeline_primeira_publicacao(driver, adapta_info)

        # ── 6. Relatório ─────────────────────────────────────────────────────
        gerar_json_relatorio()

        logging.info("[MAIN] 🎉 Automação concluída com sucesso!")
        time.sleep(5)

    except KeyboardInterrupt:
        logging.warning("\n[MAIN] Interrompido pelo usuário (Ctrl+C).")

    except Exception as e:
        logging.error(f"[MAIN] ❌ Erro fatal: {e}")
        if driver:
            salvar_screenshot(driver, "erro_fatal")
            diagnosticar_pagina(driver, "erro_fatal")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
            logging.info("[MAIN] 🛑 Driver encerrado.")


if __name__ == "__main__":
    main()
