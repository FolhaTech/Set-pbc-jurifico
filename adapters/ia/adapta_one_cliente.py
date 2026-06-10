import re
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

from core.entities import Publicacao, Analise, Agendamento
from core.enums import LadoProcesso, Urgencia, StatusAcao
from core.services.calcular_prazo import CalcularPrazo
from ports.cliente_ia import ClienteIA
from config.settings import ARQUIVO_JSON

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
            f"2. Com base na Data de Disponibilização ({data_disp}) e no prazo, calcule:\n"
            f"   - **Data Limite** = Data de Disponibilização + prazo\n"
            f"   - **Data de Agendamento** = Data Limite - 5 dias\n"
            f"3. {instrucao}\n"
            f"4. Responda SOMENTE com a tabela + resumo de agendamento.\n\n"
            f"**RESUMO DE AGENDAMENTO:**\n"
            f"- **Decisão:** {decisao_str}\n"
            f"- **Data do Agendamento:** {data_agend_sugerida}\n"
        )

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

            data_ia = re.search(
                r"Data d[oe] Agendamento[^\d]*(\d{2}/\d{2}/\d{4})",
                resposta_texto,
                re.IGNORECASE,
            )
            data_agendada_final = data_ia.group(1) if data_ia else data_agend_sugerida

            prazo_ia = re.search(
                r"Prazo Identificado[^\d]*(\d+)", resposta_texto, re.IGNORECASE
            )
            if prazo_ia:
                prazo_dias = int(prazo_ia.group(1))

            from datetime import date as date_type

            agend = calc.calcular_prazo(
                prazo_dias, publicacao.data_disponibilizacao or datetime.now().date()
            )

            return Analise(
                lado=lado,
                resumo=(
                    resposta_texto[:300] + "..."
                    if len(resposta_texto) > 300
                    else resposta_texto
                ),
                urgencia=(
                    Urgencia.ALTA
                    if agend.status_temporal.value in ("URGENTE", "ATRASADO")
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
                agendamento=agend,
                decisao_agendamento=decisao_str,
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

    def _enviar_mensagem(self, text: str) -> str:
        payload = {
            "chatId": self._chat_id or str(uuid.uuid4()),
            "modelAi": "ONE",
            "messages": [{"role": "user", "parts": [{"type": "text", "text": text}]}],
            "trigger": "user",
            "messageId": str(uuid.uuid4()),
            "isTemporaryChat": False,
        }
        if self._expert_id:
            payload["expertId"] = self._expert_id

        r = requests.post(
            f"{self.BASE_URL}/api/chat/stream/v1",
            headers=self.headers,
            json=payload,
            stream=True,
        )
        r.raise_for_status()

        full_text = []
        for line in r.iter_lines():
            if line:
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
        return "".join(full_text)

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
        try:
            r = requests.get(f"{self.BASE_URL}/api/chat/v1", headers=self.headers)
            r.raise_for_status()
            data = r.json()
            chats = data.get("data", []) if isinstance(data, dict) else data
            if chats:
                return chats[0].get("id", str(uuid.uuid4()))
        except Exception:
            pass
        return str(uuid.uuid4())

    def _list_all_experts(self, limit: int = 6000):
        r = requests.get(
            f"{self.BASE_URL}/api/expert/getAll/v1?limit={limit}",
            headers=self.headers,
        )
        r.raise_for_status()
        return r.json()

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
        r = requests.get(url, headers=self.headers)
        r.raise_for_status()
        return r.json()
