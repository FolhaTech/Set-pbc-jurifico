#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/agente_adapta_one.py
----------------------------
Integração com o Adapta ONE (expert "O PROCESSUALISTA v2").
Este módulo é OPCIONAL — funciona em paralelo ao agente_ia.py (Groq).

Fluxo:
  1. Extrai o token JWT local do Adapta ONE Desktop
  2. Localiza o expert "O PROCESSUALISTA v2"
  3. Envia cada publicação para análise em streaming
  4. Salva o resultado e o resumo de agendamento no JSON

Para usar: certifique-se de que o Adapta ONE Desktop está instalado e autenticado.
"""

import os
import sys
import json
import uuid
import time
import re
import subprocess
import unicodedata
import requests
import logging

from datetime import datetime, timedelta
from config.settings import ARQUIVO_JSON, PLANILHA_BASE

try:
    import openpyxl
except ImportError:
    openpyxl = None

# Força UTF-8 no console Windows (para emojis)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ─── Token JWT ───────────────────────────────────────────────────────────────

def auto_extract_clerk_token() -> str:
    """Tenta extrair o token do Adapta ONE via script Node.js local."""
    try:
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "extract_token.js"
        )
        # Se não existir localmente, tenta na pasta original
        if not os.path.exists(script_path):
            script_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "Automação publicação Juridico",
                "extract_token.js"
            )
        if os.path.exists(script_path):
            result = subprocess.run(
                ["node", script_path], capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            if data.get("success") and data.get("token"):
                return data["token"]
    except Exception as e:
        logging.warning(f"[ADAPTA] Falha ao extrair token via Node: {e}")
    return ""


def check_jwt_expired(token: str) -> bool:
    """Verifica se o token JWT está expirado ou próximo de expirar (< 60s)."""
    import base64
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return True
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        return payload.get("exp", 0) < time.time() + 60
    except Exception:
        return True


def renew_local_token() -> str:
    """Tenta renovar o token abrindo o Adapta ONE Desktop minimizado."""
    exe_path = r"C:\Program Files\adapta-one-agent-desktop\adapta-one-agent-desktop.exe"
    if not os.path.exists(exe_path):
        logging.warning("[ADAPTA] Executável do Adapta ONE Desktop não encontrado.")
        return ""

    logging.info("[ADAPTA] Iniciando renovação do token via Adapta ONE Desktop...")
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        subprocess.Popen([exe_path], startupinfo=si)

        start = time.time()
        while time.time() - start < 12:
            time.sleep(1)
            token = auto_extract_clerk_token()
            if token and not check_jwt_expired(token):
                logging.info("[ADAPTA] ✅ Token renovado com sucesso.")
                return token
    except Exception as e:
        logging.error(f"[ADAPTA] Erro ao renovar token: {e}")
    return ""


def get_user_id_from_token(token: str) -> str | None:
    """Decodifica o campo 'sub' (userId) de um JWT sem validar a assinatura."""
    import base64
    try:
        parts = token.split(".")
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        return payload.get("sub")
    except Exception:
        return None


# ─── Planilha Base ───────────────────────────────────────────────────────────

def _normalizar_nome(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def verificar_cliente_planilha(polo_a: str, numero_processo: str = None) -> dict:
    """
    Verifica se polo_a é nosso cliente na planilha 3. Relatório Base x Advogado.xlsx.

    Returns:
        {'e_nosso': bool, 'cliente_planilha': str|None, 'contrario': str|None}
    """
    if not openpyxl:
        return {"e_nosso": True, "cliente_planilha": None, "contrario": None}

    if not os.path.exists(PLANILHA_BASE):
        logging.warning(f"[ADAPTA] Planilha não encontrada: {PLANILHA_BASE}")
        return {"e_nosso": True, "cliente_planilha": None, "contrario": None}

    try:
        wb = openpyxl.load_workbook(PLANILHA_BASE, read_only=True, data_only=True)
        ws = wb.active
        polo_a_norm = _normalizar_nome(polo_a)
        proc_norm = (numero_processo or "").replace("-", "").replace(".", "").strip()

        for row in ws.iter_rows(min_row=2, values_only=True):
            num_proc_cel = str(row[2] or "").replace("-", "").replace(".", "").strip()
            cliente_cel  = str(row[3] or "")
            contrario_cel = str(row[9] or "")
            cliente_norm = _normalizar_nome(cliente_cel)

            if proc_norm and num_proc_cel == proc_norm:
                e_nosso = polo_a_norm in cliente_norm or cliente_norm in polo_a_norm
                return {"e_nosso": e_nosso, "cliente_planilha": cliente_cel, "contrario": contrario_cel}

            if cliente_norm and polo_a_norm and (polo_a_norm in cliente_norm or cliente_norm in polo_a_norm):
                return {"e_nosso": True, "cliente_planilha": cliente_cel, "contrario": contrario_cel}

        wb.close()
        return {"e_nosso": False, "cliente_planilha": None, "contrario": None}
    except Exception as e:
        logging.error(f"[ADAPTA] Erro ao ler planilha: {e}")
        return {"e_nosso": True, "cliente_planilha": None, "contrario": None}


# ─── Cliente Adapta ONE ───────────────────────────────────────────────────────

class AdaptaOneClient:
    BASE_URL = "https://agent.adapta.one"

    def __init__(self, clerk_token: str):
        self.clerk_token = clerk_token
        self.headers = {
            "Authorization": f"Bearer {clerk_token}",
            "Content-Type": "application/json",
            "X-Client-Platform": "desktop",
            "X-Client-OS": "windows",
        }

    def list_chats(self):
        r = requests.get(f"{self.BASE_URL}/api/chat/v1", headers=self.headers)
        r.raise_for_status()
        return r.json()

    def list_experts(self, limit: int = 6000):
        r = requests.get(f"{self.BASE_URL}/api/expert/getAll/v1?limit={limit}", headers=self.headers)
        r.raise_for_status()
        return r.json()

    def list_personal_experts(self):
        user_id = get_user_id_from_token(self.clerk_token)
        url = f"{self.BASE_URL}/api/expert/getAllByUserId/v1"
        if user_id:
            url += f"?userId={user_id}"
        r = requests.get(url, headers=self.headers)
        r.raise_for_status()
        return r.json()

    def send_message_stream(self, chat_id: str, text: str, model_ai: str = "ONE", expert_id: str = None):
        payload = {
            "chatId": chat_id,
            "modelAi": model_ai,
            "messages": [{"role": "user", "parts": [{"type": "text", "text": text}]}],
            "trigger": "user",
            "messageId": str(uuid.uuid4()),
            "isTemporaryChat": False,
        }
        if expert_id:
            payload["expertId"] = expert_id

        r = requests.post(f"{self.BASE_URL}/api/chat/stream/v1", headers=self.headers, json=payload, stream=True)
        r.raise_for_status()

        for line in r.iter_lines():
            if line:
                decoded = line.decode("utf-8").strip()
                if decoded.startswith("data:"):
                    data_json = decoded[5:].strip()
                    if data_json == "[DONE]":
                        break
                    try:
                        yield json.loads(data_json)
                    except json.JSONDecodeError:
                        yield decoded


def _extract_experts_list(resp) -> list:
    if not resp or not isinstance(resp, dict):
        return []
    data = resp.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        agents = data.get("agents")
        if isinstance(agents, list):
            return agents
    return []


def _localizar_expert(client: AdaptaOneClient, nome_expert: str = "o processualista v2") -> str | None:
    """Localiza o expert pelo nome nos experts pessoais e públicos."""
    todas = []
    for fn in [client.list_personal_experts, client.list_experts]:
        try:
            todas.extend(_extract_experts_list(fn()))
        except Exception:
            pass

    # Busca exata
    for exp in todas:
        if isinstance(exp, dict) and exp.get("name", "").strip().lower() == nome_expert:
            logging.info(f"[ADAPTA] ✅ Expert encontrado: '{exp['name']}' (ID: {exp['id']})")
            return exp["id"]

    # Busca parcial
    for exp in todas:
        if isinstance(exp, dict) and "processualista" in exp.get("name", "").lower():
            logging.info(f"[ADAPTA] ✅ Expert parcial: '{exp['name']}' (ID: {exp['id']})")
            return exp["id"]

    return None


def calcular_datas_agendamento_adapta(prazo_dias: int, data_str: str) -> dict | None:
    """Calcula datas de agendamento (data_limite = data + prazo; agendamento = limite - 5 dias)."""
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"]:
        try:
            data_disp = datetime.strptime(data_str, fmt)
            break
        except ValueError:
            continue
    else:
        return None

    hoje = datetime.now()
    data_limite = data_disp + timedelta(days=prazo_dias)
    data_agend = data_limite - timedelta(days=5)
    dias = (data_agend - hoje).days
    status = "ATRASADO" if data_agend < hoje else ("URGENTE" if dias <= 2 else "OK")

    return {
        "data_limite": data_limite.strftime("%d/%m/%Y"),
        "data_agendamento": data_agend.strftime("%d/%m/%Y"),
        "status_temporal": status,
        "dias_restantes": dias,
    }


# ─── Processamento principal ─────────────────────────────────────────────────

def processar_com_adapta_one(arquivo_json: str = ARQUIVO_JSON):
    """
    Ponto de entrada do módulo Adapta ONE.
    Lê publicacoes.json, envia cada publicação ao expert e salva os resultados.
    """
    print("=" * 60)
    print("🤖 INICIALIZANDO AGENTE ADAPTA ONE")
    print("=" * 60)

    # 1. Token
    token = auto_extract_clerk_token()
    if not token or check_jwt_expired(token):
        token = renew_local_token() or token
    if not token:
        print("❌ Token do Adapta ONE não obtido. Verifique se o desktop está aberto.")
        sys.exit(1)
    print("✅ Token obtido.")

    # 2. Cliente
    client = AdaptaOneClient(token)

    # 3. Expert
    expert_id = _localizar_expert(client)
    if not expert_id:
        print("❌ Expert 'O PROCESSUALISTA v2' não encontrado.")
        sys.exit(1)

    # 4. Chat ID
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
    print(f"💬 Chat ID: {chat_id}")

    # 5. Ler publicações
    if not os.path.exists(arquivo_json):
        print(f"❌ Arquivo '{arquivo_json}' não encontrado.")
        sys.exit(1)

    with open(arquivo_json, "r", encoding="utf-8") as f:
        publicacoes = json.load(f)

    if not isinstance(publicacoes, list):
        publicacoes = [publicacoes]

    total = len(publicacoes)
    print(f"\n📂 {total} publicações a processar.\n")

    # 6. Loop
    for idx, pub in enumerate(publicacoes, 1):
        processo  = pub.get("processo_numero", "N/A")
        conteudo  = pub.get("conteudo", "")
        if not conteudo:
            print(f"[{idx}/{total}] {processo} — sem conteúdo. Pulando.")
            continue

        print("=" * 80)
        print(f"📦 [{idx}/{total}] Processo: {processo}")
        print("=" * 80)

        # Datas
        data_disp = pub.get("data_disponibilizacao", "")
        if not data_disp or data_disp == "N/A":
            data_disp = datetime.now().strftime("%d/%m/%Y")

        analise_gemini = pub.get("analise_gemini", {})
        prazo_dias = int(
            analise_gemini.get("prazo_dias_conteudo")
            or analise_gemini.get("prazo_recomendado_dias_uteis")
            or 0
        )
        if prazo_dias == 0:
            prazo_dias = 5 if "despacho" in analise_gemini.get("tipo_publicacao", "").lower() else 15

        agendamento_info = calcular_datas_agendamento_adapta(prazo_dias, data_disp)
        if agendamento_info:
            pub["agendamento"] = agendamento_info
            pub["data_agendada"] = agendamento_info["data_agendamento"]

        # Polo A / Polo P
        campos = pub.get("conteudo_parsed", {}).get("campos", {})
        autor = campos.get("polo_a", "") or analise_gemini.get("polo_a", "") or "N/A"
        reu_raw = campos.get("polo_p", "") or analise_gemini.get("polo_p", "")
        reu = (", ".join(reu_raw) if isinstance(reu_raw, list) else reu_raw) or "N/A"

        # Verificação na planilha
        resultado = verificar_cliente_planilha(autor, processo)
        e_nosso = resultado["e_nosso"]
        pub["lado_processo"] = "nosso_cliente" if e_nosso else "operadora"
        pub["sem_providencia"] = not e_nosso
        decisao_str = "AGENDAR" if e_nosso else "SEM PROVIDÊNCIA"
        data_agend_str = agendamento_info["data_agendamento"] if agendamento_info else "N/A"

        instrucao = (
            "Esta publicação é do **nosso cliente** como polo ativo. "
            "Indique claramente a data estipulada pelo juiz e a ação que nossa equipe deve tomar."
            if e_nosso else
            "Esta publicação é relativa à **parte contrária (operadora)**. "
            "Indique que nenhuma ação ativa é necessária da nossa parte."
        )
        label = "✅ Nosso Cliente" if e_nosso else "⚪ Sem Providência (Operadora)"

        prompt = (
            f"Você é um assistente jurídico objetivo. Analise esta publicação de forma CONCISA.\n\n"
            f"**DADOS:**\n"
            f"- Data Disponibilização: {data_disp}\n"
            f"- Processo: {processo}\n"
            f"- Polo A: {campos.get('polo_a', autor)}\n"
            f"- Polo P: {reu}\n"
            f"- Classificação: {label}\n\n"
            f"**CONTEÚDO:**\n{conteudo}\n\n"
            f"**INSTRUÇÕES:**\n"
            f"1. Identifique o prazo dado pelo juiz.\n"
            f"2. Calcule: Data Limite = {data_disp} + prazo; Agendamento = Limite - 5 dias.\n"
            f"3. {instrucao}\n"
            f"4. Responda SOMENTE com a tabela + resumo de agendamento + 1 parágrafo curto.\n\n"
            f"**RESUMO DE AGENDAMENTO:**\n"
            f"- Decisão: {decisao_str}\n"
            f"- Data do Agendamento: {data_agend_str}\n"
        )

        # Streaming para o expert
        full_text = []
        try:
            stream = client.send_message_stream(chat_id=chat_id, text=prompt, expert_id=expert_id)
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

            resposta = "".join(full_text)
            pub["analise_processualista"] = resposta

            # Extrai data corrigida pela IA
            data_ia = re.search(r"Data d[oe] Agendamento[^\d]*(\d{2}/\d{2}/\d{4})", resposta, re.IGNORECASE)
            data_agend_final = data_ia.group(1) if data_ia else data_agend_str

            pub["data_agendada"] = data_agend_final
            pub["decisao_agendamento"] = decisao_str
            if agendamento_info:
                pub["agendamento"]["data_agendamento"] = data_agend_final

            pub["resumo_agendamento"] = {
                "processo":         processo,
                "decisao":          decisao_str,
                "data_agendamento": data_agend_final,
                "classificacao":    label,
                "polo_ativo":       campos.get("polo_a", autor),
                "polo_passivo":     reu,
            }

            print(f"\n{'🌟' * 30}")
            print(f"📢 [RESUMO] Processo: {processo} | Decisão: {decisao_str} | Agendamento: {data_agend_final}")
            print(f"{'🌟' * 30}\n")

        except Exception as e:
            print(f"❌ Erro ao processar {processo}: {e}")

        # Salva incrementalmente
        with open(arquivo_json, "w", encoding="utf-8") as f:
            json.dump(publicacoes, f, ensure_ascii=False, indent=2)
        print(f"✅ Salvo: {processo}")

    print("\n" + "=" * 80)
    print("🎉 PROCESSAMENTO ADAPTA ONE CONCLUÍDO!")
    print("=" * 80)
