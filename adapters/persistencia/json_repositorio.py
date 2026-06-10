import os
import json
import hashlib
import logging
from datetime import datetime, date
from typing import Optional, List

from core.entities import (
    Publicacao,
    Analise,
    Agendamento,
    ConteudoParsed,
    FlagsPublicacao,
    Advogado,
)
from core.enums import LadoProcesso, StatusTemporal, Urgencia, StatusAcao
from ports.repositorio import Repositorio
from config.settings import ARQUIVO_JSON

logger = logging.getLogger(__name__)


class JsonRepositorio(Repositorio):
    """Implementação do Repositorio usando arquivo JSON."""

    def __init__(self, arquivo: str = ARQUIVO_JSON):
        self._arquivo = arquivo
        os.makedirs(os.path.dirname(arquivo), exist_ok=True)

    def salvar(self, publicacao: Publicacao) -> None:
        publicacoes = self._carregar()
        dados = self._para_dict(publicacao)
        processo = dados.get("processo_numero", "N/A")

        if not processo or processo == "N/A":
            conteudo = dados.get("conteudo", "")
            if conteudo:
                hash_id = (
                    "TMP-"
                    + hashlib.md5(conteudo.encode("utf-8")).hexdigest()[:12].upper()
                )
                dados["processo_numero"] = hash_id
                processo = hash_id
                logger.warning(f"[JSON_REPO] Processo N/A — ID temporário: {hash_id}")
            else:
                logger.warning(
                    "[JSON_REPO] Processo N/A e sem conteúdo. Registro descartado."
                )
                return

        for i, pub in enumerate(publicacoes):
            if pub.get("processo_numero") == processo:
                publicacoes[i] = dados
                break
        else:
            publicacoes.append(dados)

        self._salvar_arquivo(publicacoes)
        logger.info(f"[JSON_REPO] Publicação salva: {processo}")

    def listar_todas(self) -> List[Publicacao]:
        dados = self._carregar()
        return [self._de_dict(d) for d in dados]

    def buscar_por_processo(self, numero: str) -> Optional[Publicacao]:
        for pub in self.listar_todas():
            if pub.processo_numero == numero:
                return pub
        return None

    # ── Conversão entities → dict ────────────────────────────────

    def _para_dict(self, pub: Publicacao) -> dict:
        d = {
            "url_pagina": pub.url_pagina,
            "data_raspagem": (
                pub.data_raspagem.isoformat() if pub.data_raspagem else None
            ),
            "processo_numero": pub.processo_numero,
            "processo_href": pub.processo_href,
            "tipo": pub.tipo,
            "badge": pub.badge,
            "data_disponibilizacao": (
                pub.data_disponibilizacao.isoformat()
                if pub.data_disponibilizacao
                else "N/A"
            ),
            "fonte_tribunal": pub.fonte_tribunal,
            "fonte_diario": pub.fonte_diario,
            "conteudo": pub.conteudo,
            "conteudo_parsed": {
                "campos": pub.conteudo_parsed.campos,
                "advogados": [
                    {"nome": a.nome, "oab": a.oab}
                    for a in pub.conteudo_parsed.advogados
                ],
                "flags": {
                    "eh_sigiloso": pub.conteudo_parsed.flags.eh_sigiloso,
                    "processo_sigiloso": pub.conteudo_parsed.flags.processo_sigiloso,
                    "consulta_autos_digitais": pub.conteudo_parsed.flags.consulta_autos_digitais,
                },
                "texto_bruto": pub.conteudo_parsed.texto_bruto,
            },
        }
        if pub.analise:
            d["lado_processo"] = pub.analise.lado.value
            d["sem_providencia"] = pub.analise.lado == LadoProcesso.OPERADORA
            d["analise_processualista"] = pub.analise.analise_completa
            if pub.analise.agendamento:
                d["agendamento"] = {
                    "data_limite": pub.analise.agendamento.data_limite.strftime(
                        "%d/%m/%Y"
                    ),
                    "data_agendamento": pub.analise.agendamento.data_agendamento.strftime(
                        "%d/%m/%Y"
                    ),
                    "status_temporal": pub.analise.agendamento.status_temporal.value,
                    "dias_restantes": pub.analise.agendamento.dias_restantes,
                }
                d["data_agendada"] = pub.analise.agendamento.data_agendamento.strftime(
                    "%d/%m/%Y"
                )
            d["decisao_agendamento"] = pub.analise.decisao_agendamento or (
                "SEM PROVIDÊNCIA"
                if pub.analise.lado == LadoProcesso.OPERADORA
                else "AGENDAR"
            )
            d["analise_gemini"] = {
                "resumo": (
                    pub.analise.resumo[:300] + "..."
                    if len(pub.analise.resumo) > 300
                    else pub.analise.resumo
                ),
                "lado_processo": pub.analise.lado.value,
                "urgencia": pub.analise.urgencia.value,
                "prazo_recomendado_dias_uteis": pub.analise.prazo_dias,
                "acao_recomendada": pub.analise.acao_recomendada,
                "requer_acao": pub.analise.requer_acao,
            }
            d["acao_executada"] = pub.analise.status_acao.value
            d["status_decidido"] = pub.analise.status_acao.value
        return d

    # ── Conversão dict → entities ────────────────────────────────

    def _de_dict(self, d: dict) -> Publicacao:
        flags = FlagsPublicacao(
            eh_sigiloso=d.get("conteudo_parsed", {})
            .get("flags", {})
            .get("eh_sigiloso", False),
            processo_sigiloso=d.get("conteudo_parsed", {})
            .get("flags", {})
            .get("processo_sigiloso", False),
            consulta_autos_digitais=d.get("conteudo_parsed", {})
            .get("flags", {})
            .get("consulta_autos_digitais", False),
        )
        advogados = [
            Advogado(nome=a.get("nome", ""), oab=a.get("oab", ""))
            for a in d.get("conteudo_parsed", {}).get("advogados", [])
        ]
        conteudo_parsed = ConteudoParsed(
            campos=d.get("conteudo_parsed", {}).get("campos", {}),
            advogados=advogados,
            flags=flags,
            texto_bruto=d.get("conteudo_parsed", {}).get("texto_bruto", ""),
        )
        data_disp = d.get("data_disponibilizacao")
        if data_disp and data_disp != "N/A":
            try:
                data_disp_parsed = datetime.strptime(data_disp, "%d/%m/%Y").date()
            except (ValueError, TypeError):
                data_disp_parsed = None
        else:
            data_disp_parsed = None

        analise = None
        lado = d.get("lado_processo")
        if lado:
            analise = Analise(
                lado=LadoProcesso(lado),
                resumo=d.get("analise_gemini", {}).get("resumo", ""),
                urgencia=Urgencia(d.get("analise_gemini", {}).get("urgencia", "MEDIA")),
                prazo_dias=d.get("analise_gemini", {}).get(
                    "prazo_recomendado_dias_uteis", 15
                ),
                acao_recomendada=d.get("analise_gemini", {}).get(
                    "acao_recomendada", ""
                ),
                requer_acao=d.get("analise_gemini", {}).get("requer_acao", False),
                fonte_ia=d.get("analise_gemini", {}).get("fonte_ia", "desconhecida"),
                analise_completa=d.get("analise_processualista"),
                agendamento=None,
                decisao_agendamento=d.get("decisao_agendamento"),
                status_acao=StatusAcao(
                    d.get("acao_executada", "Pendente revisao manual")
                ),
            )
            agend = d.get("agendamento")
            if agend:
                try:
                    analise.agendamento = Agendamento(
                        data_limite=datetime.strptime(
                            agend["data_limite"], "%d/%m/%Y"
                        ).date(),
                        data_agendamento=datetime.strptime(
                            agend["data_agendamento"], "%d/%m/%Y"
                        ).date(),
                        status_temporal=StatusTemporal(
                            agend.get("status_temporal", "OK")
                        ),
                        dias_restantes=agend.get("dias_restantes", 0),
                    )
                except (ValueError, KeyError):
                    pass

        data_raspagem = d.get("data_raspagem", "")
        try:
            dt_raspagem = (
                datetime.fromisoformat(data_raspagem)
                if data_raspagem
                else datetime.now()
            )
        except ValueError:
            dt_raspagem = datetime.now()

        return Publicacao(
            url_pagina=d.get("url_pagina", ""),
            data_raspagem=dt_raspagem,
            processo_numero=d.get("processo_numero", "N/A"),
            processo_href=d.get("processo_href"),
            tipo=d.get("tipo", "N/A"),
            badge=d.get("badge", "N/A"),
            data_disponibilizacao=data_disp_parsed,
            fonte_tribunal=d.get("fonte_tribunal", "N/A"),
            fonte_diario=d.get("fonte_diario", "N/A"),
            conteudo=d.get("conteudo", ""),
            conteudo_parsed=conteudo_parsed,
            analise=analise,
        )

    def gerar_relatorio(self) -> dict:
        import os
        from config.settings import ARQUIVO_RELATORIO
        from datetime import datetime as dt_import

        publicacoes = self._carregar()
        total = len(publicacoes)
        com_analise = sum(1 for p in publicacoes if p.get("analise_gemini"))
        sem_analise = total - com_analise

        relatorio_anterior = {}
        processos_tratados_ant = set()
        processos_sem_prov_ant = set()
        try:
            with open(ARQUIVO_RELATORIO, "r", encoding="utf-8") as f:
                relatorio_anterior = json.load(f)
            processos_tratados_ant = {
                e.get("processo")
                for e in relatorio_anterior.get("nosso_tratado", [])
                if isinstance(e, dict)
            }
            processos_sem_prov_ant = {
                e.get("processo")
                for e in relatorio_anterior.get("operadora_sem_providencia", [])
                if isinstance(e, dict)
            }
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        def _status_label(acao: str) -> str:
            mapa = {
                "Tratado": "Marcado como Tratado",
                "Sem providencia": "Marcado como Sem providencia",
                "Pendente revisao manual": "Aguardando acao manual do responsavel",
                "Falha ao marcar": "Acao necessaria (falha ao marcar no sistema)",
                "Pulado (sem analise)": "Sem analise do agente",
            }
            return mapa.get(acao, acao or "Pendente")

        nosso_tratado = list(relatorio_anterior.get("nosso_tratado", []))
        operadora_sem_prov = list(
            relatorio_anterior.get("operadora_sem_providencia", [])
        )
        pendentes_acao = []
        urgencias_nossas = []

        for pub in publicacoes:
            analise = pub.get("analise_gemini")
            if not analise:
                continue
            lado = analise.get("lado_processo", "indeterminado")
            acao = pub.get("acao_executada", "")
            processo = pub.get("processo_numero")

            decisao_agente = {
                "nosso_cliente": "Tratar",
                "operadora": "Sem providencia",
            }.get(lado, "Indeterminado")

            entry = {
                "processo": processo,
                "decisao_agente": decisao_agente,
                "lado_processo": lado,
                "status_acao": _status_label(acao),
                "urgencia": analise.get("urgencia", ""),
                "resumo": analise.get("resumo", ""),
                "acao_recomendada": analise.get("acao_recomendada", ""),
                "data_raspagem": pub.get("data_raspagem", ""),
            }

            if lado == "nosso_cliente":
                if acao == "Tratado" and processo not in processos_tratados_ant:
                    nosso_tratado.append(entry)
                    processos_tratados_ant.add(processo)
                elif acao != "Tratado":
                    pendentes_acao.append(entry)
            elif lado == "operadora":
                if acao == "Sem providencia" and processo not in processos_sem_prov_ant:
                    operadora_sem_prov.append(entry)
                    processos_sem_prov_ant.add(processo)

            agend = pub.get("agendamento")
            if agend and agend.get("status_temporal") in ("URGENTE", "ATRASADO"):
                urgencias_nossas.append(
                    {
                        "processo": processo,
                        "decisao_agente": decisao_agente,
                        "dias_restantes": agend.get("dias_restantes"),
                        "status_temporal": agend.get("status_temporal"),
                        "data_limite": agend.get("data_limite"),
                    }
                )

        urgencias_nossas.sort(key=lambda x: x.get("dias_restantes", 999))

        relatorio = {
            "timestamp": dt_import.now().isoformat(),
            "total": total,
            "com_analise": com_analise,
            "sem_analise": sem_analise,
            "nosso_tratado": nosso_tratado,
            "pendentes_acao": pendentes_acao,
            "operadora_sem_providencia": operadora_sem_prov,
            "urgencias_nossas": urgencias_nossas,
        }

        os.makedirs(os.path.dirname(ARQUIVO_RELATORIO), exist_ok=True)
        with open(ARQUIVO_RELATORIO, "w", encoding="utf-8") as f:
            json.dump(relatorio, f, ensure_ascii=False, indent=2)

        logger.info(
            f"[RELATORIO] Gerado — "
            f"{len(nosso_tratado)} tratados | "
            f"{len(pendentes_acao)} pendentes | "
            f"{len(operadora_sem_prov)} sem providencia | "
            f"{len(urgencias_nossas)} urgencias"
        )
        return relatorio

    # ── Leitura/escrita do arquivo JSON ───────────────────────────

    def _carregar(self) -> list:
        try:
            with open(self._arquivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _salvar_arquivo(self, publicacoes: list) -> None:
        with open(self._arquivo, "w", encoding="utf-8") as f:
            json.dump(publicacoes, f, ensure_ascii=False, indent=2)
