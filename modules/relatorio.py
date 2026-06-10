#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/relatorio.py
--------------------
Geração do relatório consolidado de análise das publicações.
Lê publicacoes.json e produz relatorio_analise.json com estatísticas,
listas de tratados, sem providência, pendentes e urgências.
"""

import json
import logging

from datetime import datetime
from config.settings import ARQUIVO_JSON, ARQUIVO_RELATORIO


def gerar_json_relatorio(
    arquivo_pub: str = ARQUIVO_JSON,
    arquivo_rel: str = ARQUIVO_RELATORIO,
) -> dict:
    """
    Lê publicacoes.json e gera/atualiza relatorio_analise.json.
    Mescla com relatório anterior para não perder histórico.

    Returns:
        dict com o relatório gerado.
    """
    # Carrega publicações atuais
    try:
        with open(arquivo_pub, "r", encoding="utf-8") as f:
            publicacoes = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        publicacoes = []

    # Carrega relatório anterior (para mesclar listas históricas)
    try:
        with open(arquivo_rel, "r", encoding="utf-8") as f:
            relatorio_anterior = json.load(f)
        processos_tratados_ant = {
            e.get("processo") for e in relatorio_anterior.get("nosso_tratado", [])
            if isinstance(e, dict)
        }
        processos_sem_prov_ant = {
            e.get("processo") for e in relatorio_anterior.get("operadora_sem_providencia", [])
            if isinstance(e, dict)
        }
    except (FileNotFoundError, json.JSONDecodeError):
        relatorio_anterior = {}
        processos_tratados_ant = set()
        processos_sem_prov_ant = set()

    # Contagens
    total = len(publicacoes)
    com_analise = sum(1 for p in publicacoes if p.get("analise_gemini"))
    sem_analise = total - com_analise

    # Listas (inicializa com histórico anterior)
    nosso_tratado          = list(relatorio_anterior.get("nosso_tratado", []))
    operadora_sem_prov     = list(relatorio_anterior.get("operadora_sem_providencia", []))
    pendentes_acao         = []
    urgencias_nossas       = []

    def _status_label(acao: str) -> str:
        mapa = {
            "Tratado":                  "✅ Marcado como Tratado",
            "Sem providencia":          "✅ Marcado como Sem providência",
            "Pendente revisao manual":  "⏳ Aguardando ação manual do responsável",
            "Falha ao marcar":          "⚠️ Ação necessária (falha ao marcar no sistema)",
            "Pulado (sem analise)":     "❌ Sem análise do agente",
        }
        return mapa.get(acao, acao or "Pendente")

    for pub in publicacoes:
        analise = pub.get("analise_gemini")
        if not analise:
            continue

        lado    = analise.get("lado_processo", "indeterminado")
        acao    = pub.get("acao_executada", "")
        processo = pub.get("processo_numero")

        decisao_agente = {
            "nosso_cliente": "Tratar",
            "operadora":     "Sem providência",
        }.get(lado, "Indeterminado")

        entry = {
            "processo":         processo,
            "decisao_agente":   decisao_agente,
            "lado_processo":    lado,
            "status_acao":      _status_label(acao),
            "urgencia":         analise.get("urgencia", ""),
            "resumo":           analise.get("resumo", ""),
            "acao_recomendada": analise.get("acao_recomendada", ""),
            "data_raspagem":    pub.get("data_raspagem", ""),
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

        # Urgências por agendamento
        agend = pub.get("agendamento")
        if agend and agend.get("status_temporal") in ("URGENTE", "ATRASADO"):
            urgencias_nossas.append({
                "processo":        processo,
                "decisao_agente":  decisao_agente,
                "dias_restantes":  agend.get("dias_restantes"),
                "status_temporal": agend.get("status_temporal"),
                "data_limite":     agend.get("data_limite"),
            })

    urgencias_nossas.sort(key=lambda x: x.get("dias_restantes", 999))

    relatorio = {
        "timestamp":                datetime.now().isoformat(),
        "total":                    total,
        "com_analise":              com_analise,
        "sem_analise":              sem_analise,
        "nosso_tratado":            nosso_tratado,
        "pendentes_acao":           pendentes_acao,
        "operadora_sem_providencia": operadora_sem_prov,
        "urgencias_nossas":         urgencias_nossas,
    }

    import os
    os.makedirs(os.path.dirname(arquivo_rel), exist_ok=True)
    with open(arquivo_rel, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)

    logging.info(
        f"[RELATORIO] ✅ Gerado — "
        f"{len(nosso_tratado)} tratados | "
        f"{len(pendentes_acao)} pendentes | "
        f"{len(operadora_sem_prov)} sem providência | "
        f"{len(urgencias_nossas)} urgências"
    )

    return relatorio
