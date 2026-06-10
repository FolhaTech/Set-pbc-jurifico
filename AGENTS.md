# AGENTS.md

## What this repo does

Selenium automation that scrapes legal publications from Legal One (Thomson Reuters), classifies them against a client
spreadsheet, and optionally sends analysis to Adapta ONE AI. Hexagonal (Ports & Adapters) architecture.

## Key commands

```bash
cd Set-pbc-jurifico

# Activate venv (PowerShell)
.venv\Scripts\Activate.ps1

# Install deps
pip install -r requirements.txt

# Run automation (first publication only)
python run_v2.py

# Run all publications
python run_v2.py --todas

# Run without AI (offline mode)
python run_v2.py --sem-adapta

# Limit number of publications
python run_v2.py --todas --max 10
```

## Architecture

```
Set-pbc-jurifico/
├── run_v2.py              # Entry point
├── config/
│   ├── settings.py        # All config, env vars, paths
│   └── di.py              # Dependency injection container
├── core/
│   ├── entities.py        # Publicacao, Analise, Agendamento dataclasses
│   ├── enums.py           # StatusTemporal, LadoProcesso, Urgencia, StatusAcao
│   ├── services/
│   │   ├── calcular_prazo.py    # Deadline calculation (1.4x multiplier for business days)
│   │   └── classificador_polo.py # Client vs opponent classification
│   └── use_cases/
│       ├── analisar_publicacao.py # Single publication analysis
│       └── processar_lista.py     # Batch processing loop
├── ports/                 # Interfaces (abstract)
│   ├── navegador_web.py   # NavegadorWeb protocol
│   ├── cliente_ia.py      # ClienteIA protocol
│   └── repositorio.py     # Repositorio protocol
├── adapters/              # Implementations
│   ├── web/               # Selenium driver, login, scraping, actions
│   ├── ia/                # Adapta ONE AI client
│   ├── persistencia/      # JSON file persistence
│   └── infra/             # Logging, screenshots
├── dados/                 # Output: publicacoes.json, relatorio_analise.json
├── extract_token.js       # Node.js: decrypts Adapta ONE desktop JWT token
└── requirements.txt
```

## Prerequisites

- **Python 3.12+**
- **Node.js** (for `extract_token.js` token extraction)
- **Chrome + chromedriver** (managed by undetected-chromedriver)
- **Adapta ONE Desktop** installed at `C:\Program Files\adapta-one-agent-desktop\` (for AI mode)
- **Excel spreadsheet** at `../Automação publicação Juridico/3. Relatório Base x Advogado.xlsx` (client reference)

## Environment

Copy `.env.example` to `.env` and fill:

- `THOMSON_USERNAME` / `THOMSON_PASSWORD` — Legal One login
- `ADAPTA_TOKEN` — can be left blank (auto-extracted from desktop app)

## Important quirks

- **Dual package layout**: Root `../pyproject.toml` is a stub. Real code lives in `` with its own `requirements.txt`.
- **Spreadsheet path is relative**: `PLANILHA_BASE` in `settings.py` points to `../Automação publicação Juridico/` — the
  sibling folder must exist.
- **Token extraction is Windows-specific**: `extract_token.js` reads from Windows Registry and
  `%APPDATA%\AdaptaONE\auth-session.enc`.
- **Deadline multiplier**: Business days are multiplied by 1.4 in `CalcularPrazo` to account for non-working days.
- **No tests, linting, or type checking** configured in this repo.
- **`../.venv` is at project root** (not inside ``).
