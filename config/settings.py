#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config/settings.py
------------------
Todas as configurações, constantes e caminhos da automação jurídica.
Para alterar credenciais, URLs ou parâmetros operacionais, edite SOMENTE este arquivo.
"""

import os
from dotenv import load_dotenv

# Carrega variáveis do .env automaticamente (se houver)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# ─── URLs e Credenciais ──────────────────────────────────────────────────────
URL_LOGIN = (
    "https://signon.thomsonreuters.com/?productId=L1NJ"
    "&returnto=https%3a%2f%2flogin.novajus.com.br%2fOnePass%2fLoginOnePass%2f"
    "&bhcp=1"
)
USERNAME         = "fernando_andrade"
PASSWORD         = "Tech@#$2026"
RESPONSAVEL_ALVO = "Aline Frutuoso"
DOMINIOS_VALIDOS = ["legalone.com.br", "novajus.com.br"]

# ─── Timeouts ────────────────────────────────────────────────────────────────
TIMEOUT           = 20
TIMEOUT_POS_LOGIN = 30

# ─── Pastas de saída ─────────────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_SCREENSHOTS = os.path.join(BASE_DIR, "screenshots_debug")
PASTA_HTML        = os.path.join(BASE_DIR, "debug_html")
PASTA_DADOS       = os.path.join(BASE_DIR, "dados")

# ─── Arquivos de dados ───────────────────────────────────────────────────────
ARQUIVO_JSON      = os.path.join(PASTA_DADOS, "publicacoes.json")
ARQUIVO_RELATORIO = os.path.join(PASTA_DADOS, "relatorio_analise.json")

# ─── Parâmetros da Automação ─────────────────────────────────────────────────
MAX_PUBLICACOES = 50
RPM_DELAY       = 1       # segundos entre requisições
ANTECEDENCIA_DIAS = 5     # dias antes do prazo para agendar

# ─── Planilha base ───────────────────────────────────────────────────────────
# Referência à planilha na pasta original (não movida)
PLANILHA_BASE = os.path.join(
    os.path.dirname(BASE_DIR),
    "Automação publicação Juridico",
    "3. Relatório Base x Advogado.xlsx"
)
