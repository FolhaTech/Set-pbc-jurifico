import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Optional

import requests

from core.entities import Publicacao, Analise, Agendamento
from core.enums import LadoProcesso, Urgencia, StatusAcao
from core.services.calcular_prazo import CalcularPrazo
from ports.cliente_ia import ClienteIA

logger = logging.getLogger(__name__)


class AdaptaOneCliente(ClienteIA):
    BASE_URL = "https://agent.adapta.one"

    def __init__(self, clerk_token: str):
        self.clerk_token = clerk_token
        self.headers = {
            "Authorization": f"Bearer {clerk_token}",
            "Content-Type": "application/json",
            "X-Client-Platform": "desktop",
            "X-Client-OS": "windows",
        }
        self._expert_id: Optional[str] = None
        self._chat_id: Optional[str] = None

    def analisar(self, publicacao: Publicacao, lado: LadoProcesso) -> Analise:
        """Implementação da interface ClienteIA usando o Adapta ONE."""
        campos = publicacao.conteudo_parsed.campos
        autor = campos.get("polo_a", "") or "N/A"
        reu = campos.get("polo_p", "") or "N/A"
        data_disp = (
            publicacao.data_disponibilizacao.strftime("%d/%m/%Y")
            if publicacao.data_disponibilizacao
            else "N/A"
        )
        processo = publicacao.processo_numero
        conteudo = publicacao.conteudo

        logger.info(
            f"[ADAPTA_CLIENT] Dados da publicação:\n"
            f"  Processo: {processo}\n"
            f"  Polo A (Ativo): {autor}\n"
            f"  Polo P (Passivo): {reu}\n"
            f"  Data Disponibilização: {data_disp}\n"
            f"  Lado: {lado.value}\n"
            f"  Conteúdo (200 chars): {conteudo[:200]}..."
        )

        classificacao_label = (
            "✅ Nosso Cliente"
            if lado == LadoProcesso.NOSSO_CLIENTE
            else "⚪ Sem Providência (Operadora)"
        )
        decisao_str = (
            "AGENDAR" if lado == LadoProcesso.NOSSO_CLIENTE else "SEM PROVIDÊNCIA"
        )

        calc = CalcularPrazo()
        prazo_dias = 5 if "despacho" in (publicacao.tipo or "").lower() else 15
        agendamento_fallback = calc.calcular_prazo(
            prazo_dias, publicacao.data_disponibilizacao or datetime.now().date()
        )
        data_agend_sugerida = agendamento_fallback.data_agendamento.strftime("%d/%m/%Y")

        instrucao = (
            "Esta publicação é do **nosso cliente** como polo ativo. "
            "Analise o que foi determinado e indique a ação que nossa equipe deve tomar."
            if lado == LadoProcesso.NOSSO_CLIENTE
            else "Esta publicação é relativa à **parte contrária (operadora)**. "
                 "Indique que nenhuma ação ativa é necessária da nossa parte."
        )

        prompt = (
            f"Você é um assistente jurídico objetivo. Analise esta publicação processual de forma CONCISA.\n\n"
            f"**DADOS DA PUBLICAÇÃO:**\n"
            f"- **Data de Disponibilização:** {data_disp}\n"
            f"- **Número Único:** {campos.get('numero_unico', processo)}\n"
            f"- **Polo A (Ativo):** {autor}\n"
            f"- **Polo P (Passivo):** {reu}\n"
            f"- **Classificação:** {classificacao_label}\n\n"
            f"**CONTEÚDO DA PUBLICAÇÃO:**\n{conteudo}\n\n"
            f"---\n\n"
            f"**INSTRUÇÕES:**\n"
            f"1. Identifique o prazo dado pelo juiz (em dias).\n"
            f"1b. Se o juiz determinou uma DATA ESPECÍFICA (ex: 'audiência dia 15/07/2026', "
            f"'designado o dia 20/08'), extraia e informe no formato "
            f"**Data Determinada Pelo Juiz: DD/MM/AAAA**.\n"
            f"2. Se houver data específica: Data de Agendamento = Data do juiz - 5 dias.\n"
            f"   Se NÃO houver: Data Limite = Disponibilização + prazo; Agendamento = Data Limite - 5 dias.\n"
            f"3. {instrucao}\n"
            f"4. Responda SOMENTE com a tabela + resumo de agendamento.\n\n"
            f"**RESUMO DE AGENDAMENTO:**\n"
            f"- **Decisão:** {decisao_str}\n"
            f"- **Data do Agendamento:** {data_agend_sugerida}\n"
        )

        logger.info(f"[ADAPTA_CLIENT] Prompt enviado: {prompt}")

        try:
            if not self._expert_id:
                self._expert_id = self._localizar_expert()
            if not self._chat_id:
                self._chat_id = self._obter_chat_id()

            resposta_texto = self._enviar_mensagem(prompt)
            if not resposta_texto:
                return self._analise_fallback(
                    publicacao, lado, agendamento_fallback, decisao_str
                )

            data_juiz_match = re.search(
                r"Data Determinada P[eo]lo Juiz[^\d]*(\d{2}/\d{2}/\d{4})",
                resposta_texto,
                re.IGNORECASE,
            )
            data_juiz = None
            if data_juiz_match:
                data_juiz = datetime.strptime(
                    data_juiz_match.group(1), "%d/%m/%Y"
                ).date()
                agendamento_fallback = calc.calcular_prazo_solicitado_juiz(data_juiz)
            else:
                agendamento_fallback = calc.calcular_prazo(
                    prazo_dias,
                    publicacao.data_disponibilizacao or datetime.now().date(),
                )
            prazo_ia = re.search(
                r"Prazo Identificado[^\d]*(\d+)", resposta_texto, re.IGNORECASE
            )
            if prazo_ia:
                prazo_dias = int(prazo_ia.group(1))

            return Analise(
                lado=lado,
                resumo=(
                    resposta_texto[:300] + "..."
                    if len(resposta_texto) > 300
                    else resposta_texto
                ),
                urgencia=(
                    Urgencia.ALTA
                    if agendamento_fallback.status_temporal.value
                       in ("URGENTE", "ATRASADO")
                    else Urgencia.MEDIA
                ),
                prazo_dias=prazo_dias,
                acao_recomendada=(
                    "Revisar análise processual."
                    if lado == LadoProcesso.NOSSO_CLIENTE
                    else "Sem providências necessárias."
                ),
                requer_acao=(lado == LadoProcesso.NOSSO_CLIENTE),
                fonte_ia="adapta_one",
                analise_completa=resposta_texto,
                agendamento=agendamento_fallback,
                decisao_agendamento=decisao_str,
                data_solicitada_juiz=data_juiz,
                status_acao=(
                    StatusAcao.PENDENTE
                    if lado == LadoProcesso.NOSSO_CLIENTE
                    else StatusAcao.SEM_PROVIDENCIA
                ),
            )

        except Exception as e:
            logger.error(f"[ADAPTA_CLIENT] Falha ao analisar: {e}")
            return self._analise_fallback(
                publicacao, lado, agendamento_fallback, decisao_str
            )

    def _analise_fallback(
            self,
            pub: Publicacao,
            lado: LadoProcesso,
            agendamento: Agendamento,
            decisao: str,
    ) -> Analise:
        return Analise(
            lado=lado,
            resumo="Análise offline baseada na planilha.",
            urgencia=Urgencia.MEDIA,
            prazo_dias=15,
            acao_recomendada=(
                "Revisar análise processual."
                if lado == LadoProcesso.NOSSO_CLIENTE
                else "Sem providências necessárias."
            ),
            requer_acao=(lado == LadoProcesso.NOSSO_CLIENTE),
            fonte_ia="offline",
            agendamento=agendamento,
            decisao_agendamento=decisao,
            status_acao=(
                StatusAcao.PENDENTE
                if lado == LadoProcesso.NOSSO_CLIENTE
                else StatusAcao.SEM_PROVIDENCIA
            ),
        )

    # ── Métodos internos do Adapta ONE ───────────────────────────

    def _localizar_expert(self, nome: str = "o processualista v2") -> Optional[str]:
        for fn in [self._list_personal_experts, self._list_all_experts]:
            try:
                resp = fn()
                data = resp.get("data", []) if isinstance(resp, dict) else resp
                if isinstance(data, dict):
                    data = data.get("agents", [])
                for exp in data:
                    if isinstance(exp, dict):
                        n = exp.get("name", "").strip().lower()
                        if n == nome or "processualista" in n:
                            logger.info(
                                f"[ADAPTA_CLIENT] Expert encontrado: '{exp.get('name')}' (ID: {exp['id']})"
                            )
                            return exp["id"]
            except Exception:
                pass
        return None

    def _obter_chat_id(self) -> str:
        for tentativa in range(2):
            try:
                r = requests.get(f"{self.BASE_URL}/api/chat/v1", headers=self.headers, timeout=15)
                if r.status_code == 401 and tentativa == 0:
                    logger.warning("[ADAPTA_CLIENT] 401 em _obter_chat_id. Renovando token...")
                    if self._renovar_token():
                        continue
                    break
                r.raise_for_status()
                data = r.json()
                chats = data.get("data", []) if isinstance(data, dict) else data
                if chats:
                    chat_id = chats[0].get("id", str(uuid.uuid4()))
                    logger.info(f"[ADAPTA_CLIENT] Chat ID obtido: {chat_id}")
                    return chat_id
            except Exception:
                break
        fallback = str(uuid.uuid4())
        logger.warning(f"[ADAPTA_CLIENT] Fallback Chat ID: {fallback}")
        return fallback

    def _list_all_experts(self, limit: int = 100):
        for tentativa in range(2):
            try:
                r = requests.get(
                    f"{self.BASE_URL}/api/expert/getAll/v1?limit={limit}",
                    headers=self.headers,
                    timeout=15,
                )
                if r.status_code == 401 and tentativa == 0:
                    logger.warning("[ADAPTA_CLIENT] 401 em _list_all_experts. Renovando token...")
                    if self._renovar_token():
                        continue
                    break
                r.raise_for_status()
                return r.json()
            except Exception:
                break
        return {"data": []}

    def _list_personal_experts(self):
        import base64

        parts = self.clerk_token.split(".")
        if len(parts) != 3:
            return {"data": []}
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        user_id = payload.get("sub")
        url = f"{self.BASE_URL}/api/expert/getAllByUserId/v1"
        if user_id:
            url += f"?userId={user_id}"
        for tentativa in range(2):
            try:
                r = requests.get(url, headers=self.headers, timeout=15)
                if r.status_code == 401 and tentativa == 0:
                    logger.warning("[ADAPTA_CLIENT] 401 em _list_personal_experts. Renovando token...")
                    if self._renovar_token():
                        # Rebuild URL in case user_id changed
                        parts_new = self.clerk_token.split(".")
                        if len(parts_new) == 3:
                            p_b64 = parts_new[1] + "=" * (-len(parts_new[1]) % 4)
                            p_new = json.loads(base64.urlsafe_b64decode(p_b64).decode("utf-8"))
                            uid_new = p_new.get("sub")
                            if uid_new:
                                url = f"{self.BASE_URL}/api/expert/getAllByUserId/v1?userId={uid_new}"
                        continue
                    break
                r.raise_for_status()
                return r.json()
            except Exception:
                break
        return {"data": []}

    def enviar_mensagem(self, text: str) -> str:
        if not self._expert_id:
            self._expert_id = self._localizar_expert()
        if not self._chat_id:
            self._chat_id = self._obter_chat_id()
        return self._enviar_mensagem(text)

    def _enviar_mensagem(self, text: str, _retry: bool = False) -> str:
        payload = {
            "chatId": self._chat_id or str(uuid.uuid4()),
            "modelAi": "ONE",
            "messages": [{"role": "user", "parts": [{"type": "text", "text": text}]}],
            "trigger": "user",
            "messageId": str(uuid.uuid4()),
            "isTemporaryChat": False,
        }
        logger.info(f"[ADAPTA_CLIENT] === PAYLOAD ENVIADO ===\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

        if self._expert_id:
            payload["expertId"] = self._expert_id

        r = requests.post(
            f"{self.BASE_URL}/api/chat/stream/v1",
            headers=self.headers,
            json=payload,
            stream=True,
            timeout=(20, 120)
        )

        if r.status_code == 401 and not _retry:
            logger.warning("[ADAPTA_CLIENT] Token expirado (401). Renovando...")
            novo_token = self._renovar_token()
            if novo_token:
                logger.info("[ADAPTA_CLIENT] Token renovado. Reynoldsando requisição...")
                return self._enviar_mensagem(text, _retry=True)
            logger.error("[ADAPTA_CLIENT] Falha ao renovar token. Retornando vazio.")
            return ""

        r.raise_for_status()

        full_text = []
        CHUNK_TIMEOUT = 90

        last_chunk_time = time.time()
        for line in r.iter_lines(chunk_size=512):
            now = time.time()
            if line:
                last_chunk_time = now
                decoded = line.decode("utf-8").strip()
                if decoded.startswith("data:"):
                    data_json = decoded[5:].strip()
                    if data_json == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_json)
                        if chunk.get("type") == "reasoning-delta":
                            continue
                        delta = chunk.get("delta", "") or chunk.get("text", "")
                        if delta:
                            full_text.append(delta)
                    except json.JSONDecodeError:
                        pass
            elif now - last_chunk_time > CHUNK_TIMEOUT:
                logger.warning(f"[ADAPTA_CLIENT] Timeout de chunk recebido. Finalizando...")
                break
        resposta_final = "".join(full_text).strip()
        logger.info(f"[ADAPTA_CLIENT] Resposta do Expert: '{resposta_final[:200]}...'")
        return resposta_final

    def _renovar_token(self) -> str | None:
        try:
            from config.di import obter_token_adapta, verificar_token_expirado, renovar_token
            token = obter_token_adapta()
            if token and not verificar_token_expirado(token):
                self.clerk_token = token
                self.headers["Authorization"] = f"Bearer {token}"
                logger.info("[ADAPTA_CLIENT] ✅ Token renovado via extract_token.js")
                return token

            logger.info("[ADAPTA_CLIENT] Token extraído expirado. Abrindo desktop app...")
            token = renovar_token()
            if token:
                self.clerk_token = token
                self.headers["Authorization"] = f"Bearer {token}"
                logger.info("[ADAPTA_CLIENT] ✅ Token renovado via desktop app")
                return token

            logger.error("[ADAPTA_CLIENT] ❌ Não foi possível renovar o token.")
            return None
        except Exception as e:
            logger.error(f"[ADAPTA_CLIENT] Erro ao renovar token: {e}")
            return None
