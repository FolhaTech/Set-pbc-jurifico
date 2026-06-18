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

# Run automation (default: all publications with skip)
python run_v2.py

# Process first publication only (no skip check)
python run_v2.py --primeira

# Run without AI (offline mode — skip still active)
python run_v2.py --sem-adapta

# Limit number of publications
python run_v2.py --max 10

# Verify planilha path (critical — script halts if missing)
python -c "from config.settings import PLANILHA_BASE; import os; print(f'{PLANILHA_BASE}\nExists: {os.path.exists(PLANILHA_BASE)}')"

# Diagnose why a process isn't being skipped
python debug_skip.py
```

## Architecture

```
Set-pbc-jurifico/
├── run_v2.py              # Entry point (default: batch with skip)
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
│       ├── analisar_publicacao.py # Single publication analysis (no skip)
│       └── processar_lista.py     # Batch loop with skip + index tracking
├── ports/                 # Interfaces (abstract)
│   ├── navegador_web.py   # NavegadorWeb: login, navigate, filter, scrape, actions, fechar_painel_detalhes
│   ├── cliente_ia.py      # ClienteIA protocol
│   └── repositorio.py     # Repositorio: salvar, listar_todas, buscar_por_processo, gerar_relatorio
├── adapters/              # Implementations
│   ├── web/               # Selenium driver, login, scraping, actions
│   ├── ia/                # Adapta ONE AI client
│   ├── persistencia/      # JSON file persistence
│   └── infra/             # Logging, screenshots
├── dados/                 # Output: publicacoes.json (skip database), relatorio_analise.json
├── debug_skip.py          # Diagnoses skip logic (standalone, no browser)
├── extract_token.js       # Node.js: decrypts Adapta ONE desktop JWT token
└── requirements.txt
```

## Prerequisites

- **Python 3.12+**
- **Node.js** (for `extract_token.js` token extraction)
- **Chrome + chromedriver** (managed by undetected-chromedriver)
- **Adapta ONE Desktop** installed at `C:\Program Files\adapta-one-agent-desktop\` (for AI mode)
- **openpyxl** (`pip install openpyxl`) — script raises `ImportError` if missing
- **Excel spreadsheet**: `3. Relatório Base x Advogado.xlsx` with columns: C=processo, D=cliente, J=parte contrária

## Environment

Copy `.env.example` to `.env` and fill:

- `THOMSON_USERNAME` / `THOMSON_PASSWORD` — Legal One login
- `ADAPTA_TOKEN` — can be left blank (auto-extracted from desktop app)
- `PLANILHA_BASE` — full path to spreadsheet (optional; auto-detected by walking up 4 dirs from `config/`)

## Skip system (critical — avoid regressions)

### How it works

`ProcessarLista._ja_foi_processado(pub)` runs BEFORE analysis for every publication. It checks `dados/publicacoes.json`:

1. `buscar_por_processo(numero)` — normalized lookup (strips `.` and `-`)
2. Returns `True` (skip) if the process has **both analysis AND agendamento** — OR if `status_acao` is `SEM_PROVIDENCIA` or `TRATADO`
3. Otherwise returns `False` → publication is processed normally and saved to JSON for future skip

### Skip is only active with `--todas`-equivalent path (default)

The `else` branch in `run_v2.py` (`--primeira`) uses `AnalisarPublicacao.executar()` directly — **no skip check**. Only `ProcessarLista.executar_todas()` calls `_ja_foi_processado`.

### To force reprocess a process

Remove its entry from `dados/publicacoes.json`.

## Scraper index behavior (critical — avoid infinite loops)

`SeleniumNavegador.raspar_proxima_publicacao()` uses `self._indice_atual` to track position in the publication list:

- Picks `items[self._indice_atual]` instead of always `items[0]`
- Increments `_indice_atual` after each scrape
- When `_indice_atual >= len(items)`, returns `None` (loop breaks)
- `_indice_atual` is reset to `0` in `aplicar_filtros()` only

**Never** reset `_indice_atual` inside `raspar_proxima_publicacao` when reaching end of list — this causes infinite loops.

## `fechar_painel_detalhes()` — when to call

`SeleniumNavegador.fechar_painel_detalhes()` dispatches Escape key + clicks modal masks. It is declared on `NavegadorWeb` interface.

**Call it** in `processar_lista.py` before every `continue` (skip path). This returns to publication list so the next scrape sees fresh items.

**Never call it** inside `AnalisarPublicacao._executar_acao()` — `marcar_sem_providencia()` and `abrir_e_criar_compromisso()` need the detail panel open.

## Important quirks

- **Spreadsheet is REQUIRED, configurable via `.env`**: If the spreadsheet is missing, the script **halts with error**. Set `PLANILHA_BASE` in `.env`.
- **`openpyxl` must be installed**: Script raises `ImportError` if missing.
- **Lookup dropdowns must stay OPEN during IA calls**: The code opens the Description lookup, reads options, then calls Adapta ONE with the dropdown still open. Closing it (ESC) before the IA call causes chromedriver crashes.
- **Tipo field uses a lookuptree, not a standard lookup**: `<div data-val-control="lookuptree">` with inputs `TipoText`/`TipoId`. Options are raw text from popup, classified by IA, set via JS. If IA returns "N/A", "Diversos" is restored.
- **IA client public method**: `AdaptaOneCliente.enviar_mensagem(text)` — wraps expert/chat resolution. Never call `send_message_stream` or `_enviar_prompt`.
- **Container init order**: `Container.navegador` forces `cliente_ia` to init first (line `_ = self.cliente_ia`).
- **Deadline multiplier**: Business days × 1.4 in `CalcularPrazo` for calendar day conversion.
- **Token extraction is Windows-specific**: `extract_token.js` reads `%APPDATA%\AdaptaONE\auth-session.enc`.
- **No tests, linting, or type checking** configured in this repo.
- **`../.venv` is at project root** (not inside the code dir).
- **Double-save on batch path**: `AnalisarPublicacao.executar()` calls `_repo.salvar()` internally (line 42), and `executar_todas` calls it again. Harmless but worth knowing.
