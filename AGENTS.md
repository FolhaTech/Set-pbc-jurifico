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

# Verify planilha path (critical — script halts if missing)
python -c "from config.settings import PLANILHA_BASE; import os; print(f'{PLANILHA_BASE}\nExists: {os.path.exists(PLANILHA_BASE)}')"
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
- **openpyxl** (`pip install openpyxl`) — script errors out if missing
- **Excel spreadsheet**: `3. Relatório Base x Advogado.xlsx` with columns: C=processo, D=cliente, J=parte contrária

## Environment

Copy `.env.example` to `.env` and fill:

- `THOMSON_USERNAME` / `THOMSON_PASSWORD` — Legal One login
- `ADAPTA_TOKEN` — can be left blank (auto-extracted from desktop app)
- `PLANILHA_BASE` — full path to spreadsheet (optional; auto-detected by walking up 4 dirs from `config/`)

## Important quirks

- **Spreadsheet is REQUIRED, configurable via `.env`**: If the spreadsheet is missing, the script **halts with error** (no longer silently defaults `e_nosso=True`). Set `PLANILHA_BASE` in `.env` or ensure `Automação publicação Juridico/3. Relatório Base x Advogado.xlsx` exists at `../../` from `config/`.
- **`openpyxl` must be installed**: Script raises `ImportError` if missing.
- **Lookup dropdowns must stay OPEN during IA calls**: The code opens the Description lookup, reads options, then calls the Adapta ONE IA with the dropdown still open. Closing it (ESC) before the IA call causes chromedriver crashes when trying to re-open — elements become stale.
- **Tipo field uses a lookuptree, not a standard lookup**: The HTML structure is `<div data-val-control="lookuptree">` with inputs `TipoText`/`TipoId` (not `#Tipo`). Options are extracted as raw text from the popup, classified by IA, then set via JS (`input.value = ...` + `dispatchEvent`). If IA returns "N/A", "Diversos" is restored.
- **IA client public method**: `AdaptaOneCliente.enviar_mensagem(text)` — wraps expert/chat resolution + `_enviar_mensagem`. Never call `send_message_stream` (doesn't exist) or `_enviar_prompt`.
- **Container init order**: `Container.navegador` forces `cliente_ia` to init first (line `_ = self.cliente_ia`). This ensures `AdaptaOneCliente` is created before `SeleniumNavegador`.
- **Deadline multiplier**: Business days are multiplied by 1.4 in `CalcularPrazo` to account for non-working days.
- **Dual package layout**: Root `../pyproject.toml` is a stub. Real code lives in this dir with its own `requirements.txt`.
- **Token extraction is Windows-specific**: `extract_token.js` reads from Windows Registry and `%APPDATA%\AdaptaONE\auth-session.enc`.
- **No tests, linting, or type checking** configured in this repo.
- **`../.venv` is at project root** (not inside the code dir).
