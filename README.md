# Automação de Publicações Jurídicas — Legal One (v2 Hexagonal)

Automação Selenium que acessa o sistema **Legal One** (Thomson Reuters / NovaJus), extrai publicações processuais, classifica automaticamente se o processo é do escritório ou da parte contrária (operadora), envia o conteúdo para análise via **Adapta ONE** (IA) e agenda compromissos ou marca como "Sem providência" diretamente no sistema.

---

## Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Pré-requisitos](#pré-requisitos)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Uso](#uso)
- [Fluxo de Execução](#fluxo-de-execução)
- [Modelo de Dados](#modelo-de-dados)
- [Estrutura de Diretórios](#estrutura-de-diretórios)
- [Módulos Detalhados](#módulos-detalhados)
- [Arquivos de Saída](#arquivos-de-saída)
- [Solução de Problemas](#solução-de-problemas)

---

## Visão Geral

O sistema automatiza o ciclo completo de tratamento de publicações jurídicas:

1. **Login** no Legal One via credenciais Thomson Reuters
2. **Navegação** até a seção de Publicações
3. **Filtro** por período (60 dias) e responsável ("Aline Frutuoso")
4. **Scraping** do conteúdo de cada publicação (processo, polo, advogados, prazos)
5. **Classificação** automática: nosso cliente × parte contrária (via planilha Excel)
6. **Análise IA** via Adapta ONE: prazos, ação recomendada, urgência
7. **Ação no sistema**: criar compromisso (nosso cliente) ou marcar "Sem providência" (operadora)
8. **Persistência** em JSON e geração de relatório consolidado

---

## Arquitetura

O projeto segue o padrão **Hexagonal (Ports & Adapters)**:

```
┌─────────────────────────────────────────────────┐
│                   CORE                          │
│  entities / enums / services / use_cases        │
│  ─────────────────────────────────────────────  │
│  Lógica de negócio pura, sem dependência        │
│  de frameworks externos.                        │
├──────────────┬──────────────┬───────────────────┤
│   PORTS      │              │                   │
│ (interfaces) │              │                   │
│              │              │                   │
│ NavegadorWeb │ ClienteIA    │ Repositorio       │
│              │              │                   │
├──────────────┴──────────────┴───────────────────┤
│                ADAPTERS                         │
│                                                 │
│ web/              │  ia/           │  persistencia/ │
│ (Selenium)        │  (Adapta ONE)  │  (JSON)       │
│                   │                │               │
│ driver_setup.py   │ adapta_one_    │ json_         │
│ login.py          │   cliente.py   │  repositorio.py│
│ navegacao.py      │                │               │
│ scraper.py        │                │               │
│ acoes.py          │                │               │
│ selenium_         │                │               │
│   navegador.py    │                │               │
└─────────────────────────────────────────────────┘
```

**Ports** (interfaces abstratas) definem os contratos. **Adapters** implementam esses contratos com tecnologias concretas. O **Core** não conhece os adapters — ele depende apenas das ports.

---

## Pré-requisitos

| Requisito | Versão mínima | Observação |
|-----------|---------------|------------|
| Python | 3.12+ | `requires-python = ">=3.12"` no `pyproject.toml` |
| Node.js | 18+ | Necessário para `extract_token.js` (extração de token JWT) |
| Google Chrome | Qualquer estável | O `undetected-chromedriver` gerencia o chromedriver automaticamente |
| Adapta ONE Desktop | Instalado | Caminho padrão: `C:\Program Files\adapta-one-agent-desktop\adapta-one-agent-desktop.exe` |
| Planilha Excel | — | `../Automação publicação Juridico/3. Relatório Base x Advogado.xlsx` |

---

## Instalação

```powershell
# 1. Navegar até a raiz do projeto
cd set-pbc-juridico

# 2. Ativar o ambiente virtual
.venv\Scripts\Activate.ps1

# 3. Instalar dependências
pip install -r Set-pbc-jurifico\requirements.txt
```

**Dependências principais:**

| Pacote | Finalidade |
|--------|------------|
| `selenium` | Automação do navegador Chrome |
| `undetected-chromedriver` | Chrome driver que evita detecção de bots |
| `groq` | Cliente API para IA (disponível mas não utilizado diretamente no fluxo principal) |
| `python-dotenv` | Carregamento de variáveis de ambiente do arquivo `.env` |
| `requests` | Requisições HTTP para a API do Adapta ONE |
| `openpyxl` | Leitura da planilha Excel de referência de clientes |

---

## Configuração

### Arquivo `.env`

Copie o `.env.example` para `.env` na pasta `Set-pbc-jurifico/`:

```powershell
Copy-Item .env.example .env
```

Preencha as variáveis:

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `THOMSON_USERNAME` | Sim | Usuário de login do Legal One (Thomson Reuters) |
| `THOMSON_PASSWORD` | Sim | Senha do login do Legal One |
| `ADAPTA_TOKEN` | Não | Token JWT do Adapta ONE. Se vazio, o sistema tenta extraí-lo automaticamente do app desktop |

### Arquivo `config/settings.py`

Todas as constantes operacionais ficam neste arquivo. **Edite SOMENTE este arquivo** para alterar parâmetros:

```python
# Credenciais (lidas do .env)
USERNAME = os.getenv("THOMSON_USERNAME", "")
PASSWORD = os.getenv("THOMSON_PASSWORD", "")

# Responsável alvo nos filtros
RESPONSAVEL_ALVO = "Aline Frutuoso"

# Timeouts (segundos)
TIMEOUT = 20              # Timeout padrão de element wait
TIMEOUT_POS_LOGIN = 30    # Timeout pós-login (aguarda SPA)

# Automação
MAX_PUBLICACOES = 50      # Limite padrão de publicações por execução
RPM_DELAY = 1             # Segundos entre requisições
ANTECEDENCIA_DIAS = 5     # Dias antes do prazo para agendar

# Caminhos de saída (calculados automaticamente)
PASTA_SCREENSHOTS = "<raiz>/screenshots_debug"
PASTA_HTML = "<raiz>/debug_html"
PASTA_DADOS = "<raiz>/dados"
```

### Planilha de Referência

O sistema espera uma planilha Excel em:
```
../Automação publicação Juridico/3. Relatório Base x Advogado.xlsx
```

A planilha deve conter (nas colunas esperadas):
- **Coluna C (índice 2)**: Número do processo
- **Coluna D (índice 3)**: Nome do cliente
- **Coluna J (índice 9)**: Nome da parte contrária

A verificação normaliza textos (remove acentos, lowercase) para comparação flexível.

---

## Uso

### Modo Padrão — Primeira Publicação

```powershell
cd Set-pbc-jurifico
python run_v2.py
```

Processa apenas a primeira publicação da fila. Ideal para testes e validação.

### Todas as Publicações

```powershell
python run_v2.py --todas
```

Processa todas as publicações disponíveis (até o limite de `MAX_PUBLICACOES`).

### Modo Offline (sem IA)

```powershell
python run_v2.py --sem-adapta
```

Desativa a integração com Adapta ONE. A análise é feita localmente com dados da planilha. Útil quando o token do Adapta ONE não está disponível.

### Combinações

```powershell
# Todas as publicações em modo offline
python run_v2.py --todas --sem-adapta

# Limitar a 10 publicações
python run_v2.py --todas --max 10

# Primeira publicação com IA
python run_v2.py
```

### Resumo dos Flags

| Flag | Efeito | Padrão |
|------|--------|--------|
| `--todas` | Processa todas as publicações (não apenas a primeira) | `False` |
| `--sem-adapta` | Desativa envio ao Adapta ONE (modo offline) | `False` (IA ativa) |
| `--max N` | Limite máximo de publicações a processar | `50` (de `settings.py`) |

---

## Fluxo de Execução

```
run_v2.py main()
    │
    ├── 1. configurar_logging()
    │       Cria pastas screenshots_debug/ e debug_html/
    │       Configura logging básico (INFO level)
    │
    ├── 2. Container(usar_ia=True/False)
    │       Monta dependências sob demanda (lazy properties):
    │       ├── NavegadorWeb → SeleniumNavegador
    │       ├── Repositorio → JsonRepositorio
    │       ├── ClienteIA → AdaptaOneCliente (se usar_ia=True)
    │       ├── CalcularPrazo
    │       └── ClassificadorPolo
    │
    ├── 3. nav.login()
    │       Acessa URL_LOGIN → Preenche Username/Password → Clica SignIn
    │       Aguarda redirecionamento para domínio legalone.com.br
    │       Aguarda 10s para SPA estabilizar
    │       Salva screenshot diagnóstico "pos_login"
    │
    ├── 4. nav.navegar_para_publicacoes()
    │       Tenta多种策略 para acessar a página de publicações:
    │       ├── href do menu #menuPublicationManagement
    │       ├── Clique no menu
    │       ├── XPaths/CSS de fallback
    │       └── URL hardcoded: https://firm.legalone.com.br/publications
    │       Salva screenshot diagnóstico "pos_publicacoes"
    │
    ├── 5. nav.aplicar_filtros()
    │       ├── selecionar_periodo_60_dias()  → Botão "Últimos 60 dias"
    │       ├── abrir_mais_filtros()          → Expandir painel lateral
    │       ├── selecionar_responsavel()      → "Aline Frutuoso"
    │       └── aplicar_filtros()             → Botão "Aplicar"
    │
    └── 6. Processamento (single ou batch)
            │
            ├── [Single] nav.raspar_proxima_publicacao()
            │   → verificar_cliente_planilha()
            │   → AnalisarPublicacao.executar(pub, e_nosso)
            │
            └── [Batch] ProcessarLista.executar_todas()
                Para cada publicação:
                    1. nav.raspar_proxima_publicacao()
                    2. verificar_cliente_planilha(polo_a, processo)
                    3. AnalisarPublicacao.executar(pub, e_nosso)
                    4. repositorio.salvar(pub)
```

### Detalhe: Análise de Publicação

```
AnalisarPublicacao.executar(pub, e_nosso)
    │
    ├── ClassificadorPolo.classificar(e_nosso)
    │   → LadoProcesso.NOSSO_CLIENTE ou LadoProcesso.OPERADORA
    │
    ├── _obter_analise(pub, lado)
    │   ├── [Se IA disponível] → AdaptaOneCliente.analisar(pub, lado)
    │   │   → Monta prompt com dados da publicação
    │   │   → Envia via streaming para Adapta ONE API
    │   │   → Parseia resposta (prazo, data agendamento)
    │   │   → Fallback se falhar
    │   │
    │   └── [Offline] → _analise_offline(pub, lado)
    │       → Análise estática: prazo=15d, urgência=MEDIA
    │
    ├── CalcularPrazo.calcular_prazo(prazo_dias, data_disp)
    │   → data_limite = data_disp + (prazo_dias × 1.4)
    │   → data_agendamento = data_limite - 5 dias
    │   → Status: OK / URGENTE / ATRASADO
    │
    └── _executar_acao(pub)
        ├── [OPERADORA] → nav.marcar_sem_providencia()
        │   → Abre dropdown "Pendente" → Seleciona "Sem providências"
        │
        └── [NOSSO_CLIENTE] → nav.abrir_e_criar_compromisso(pub, analise)
            → Clica no link do processo (nova aba)
            → Aba "Compromissos e tarefas" → "Novo compromisso"
            → Lookup de descrição (classificado por IA)
            → Retorna para aba original
```

---

## Modelo de Dados

### Entidades (`core/entities.py`)

```python
@dataclass
class Publicacao:
    url_pagina: str                    # URL da página da publicação
    data_raspagem: datetime            # Data/hora do scraping
    processo_numero: str               # Número CNJ do processo
    processo_href: Optional[str]       # Link para detalhes do processo
    tipo: str                          # Tipo da publicação
    badge: str                         # Badge/classificação visual
    data_disponibilizacao: Optional[date]  # Data de disponibilização
    fonte_tribunal: str                # Tribunal de origem
    fonte_diario: str                  # Diário de publicação
    conteudo: str                      # Texto bruto da publicação
    conteudo_parsed: ConteudoParsed    # Conteúdo estruturado
    analise: Optional[Analise]         # Resultado da análise

@dataclass
class ConteudoParsed:
    campos: dict                       # Campos extraídos (polo_a, polo_p, etc.)
    advogados: list[Advogado]          # Lista de advogados com OAB
    flags: FlagsPublicacao             # Flags (sigiloso, autos digitais)
    texto_bruto: str                   # Texto original completo

@dataclass
class Analise:
    lado: LadoProcesso                # NOSSO_CLIENTE ou OPERADORA
    resumo: str                        # Resumo da análise
    urgencia: Urgencia                 # ALTA / MEDIA / BAIXA
    prazo_dias: int                    # Prazo em dias
    acao_recomendada: str              # Ação recomendada
    requer_acao: bool                  # Se requer ação do escritório
    fonte_ia: str                      # Fonte: "adapta_one" ou "offline"
    analise_completa: Optional[str]    # Texto completo da resposta IA
    agendamento: Optional[Agendamento] # Datas de agendamento
    decisao_agendamento: Optional[str] # "AGENDAR" ou "SEM PROVIDÊNCIA"
    status_acao: StatusAcao            # PENDENTE / TRATADO / SEM_PROVIDENCIA / FALHA

@dataclass
class Agendamento:
    data_limite: date                  # Prazo final
    data_agendamento: date             # Data para agendar (5 dias antes)
    status_temporal: StatusTemporal    # OK / URGENTE / ATRASADO
    dias_restantes: int                # Dias restantes até agendamento
```

### Enums (`core/enums.py`)

```python
class LadoProcesso(Enum):
    NOSSO_CLIENTE = "nosso_cliente"    # Processo em que somos Polo A
    OPERADORA = "operadora"            # Processo da parte contrária

class StatusTemporal(Enum):
    OK = "OK"                          # Prazo tranquilo
    URGENTE = "URGENTE"                # Até 2 dias restantes
    ATRASADO = "ATRASADO"              # Prazo já vencido

class Urgencia(Enum):
    ALTA = "ALTA"                      # Urgência alta
    MEDIA = "MEDIA"                    # Urgência média
    BAIXA = "BAIXA"                    # Urgência baixa

class StatusAcao(Enum):
    SEM_PROVIDENCIA = "Sem providencia"
    PENDENTE = "Pendente revisao manual"
    TRATADO = "Tratado"
    FALHA = "Falha ao marcar"
```

---

## Estrutura de Diretórios

```
set-pbc-juridico/
├── pyproject.toml                          # Stub (projeto raiz vazio)
├── uv.lock                                 # Lockfile do uv
├── .venv/                                  # Ambiente virtual (na raiz do repo)
├── AGENTS.md                               # Instruções para agentes AI
│
└── Set-pbc-jurifico/                       # Código da aplicação
    ├── README.md                           # Este arquivo
    ├── .env                                # Variáveis de ambiente (não versionado)
    ├── .env.example                        # Template das variáveis
    ├── .gitignore                          # Ignorados: __pycache__, .env, venv
    ├── requirements.txt                    # Dependências Python
    ├── run_v2.py                           # Ponto de entrada
    ├── extract_token.js                    # Script Node.js: descriptografa token JWT
    │
    ├── config/
    │   ├── __init__.py
    │   ├── settings.py                     # Configurações, constantes, caminhos
    │   └── di.py                           # Injeção de dependências (Container)
    │
    ├── core/
    │   ├── __init__.py
    │   ├── entities.py                     # Dataclasses: Publicacao, Analise, etc.
    │   ├── enums.py                        # Enums: LadoProcesso, Urgencia, etc.
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── calcular_prazo.py           # Cálculo de prazos com multiplicador 1.4x
    │   │   └── classificador_polo.py       # Classificação: nosso cliente × operadora
    │   └── use_cases/
    │       ├── __init__.py
    │       ├── analisar_publicacao.py      # Caso de uso: analisar 1 publicação
    │       └── processar_lista.py          # Caso de uso: processar lista de publicações
    │
    ├── ports/
    │   ├── __init__.py
    │   ├── navegador_web.py                # Interface: login, navegar, raspar, ações
    │   ├── cliente_ia.py                   # Interface: analisar publicação
    │   └── repositorio.py                  # Interface: salvar, listar, buscar
    │
    ├── adapters/
    │   ├── web/
    │   │   ├── __init__.py
    │   │   ├── driver_setup.py             # Configuração do Chrome/undetected
    │   │   ├── login.py                    # Login no Thomson Reuters
    │   │   ├── navegacao.py                # Navegação e filtros
    │   │   ├── scraper.py                  # Extração de dados da publicação
    │   │   ├── acoes.py                    # Ações: marcar status, criar compromisso
    │   │   └── selenium_navegador.py       # Adapter que implementa NavegadorWeb
    │   │
    │   ├── ia/
    │   │   ├── __init__.py
    │   │   └── adapta_one_cliente.py       # Adapter que implementa ClienteIA
    │   │
    │   ├── persistencia/
    │   │   ├── __init__.py
    │   │   └── json_repositorio.py         # Adapter que implementa Repositorio
    │   │
    │   └── infra/
    │       ├── __init__.py
    │       └── logging_utils.py            # Logging, screenshots, diagnóstico HTML
    │
    ├── dados/
    │   ├── publicacoes.json                # Dados persistidos das publicações
    │   └── relatorio_analise.json          # Relatório consolidado
    │
    ├── screenshots_debug/                  # Screenshots de diagnóstico (auto-gerado)
    └── debug_html/                         # HTMLs de diagnóstico (auto-gerado)
```

---

## Módulos Detalhados

### `config/di.py` — Injeção de Dependências

O Container monta todas as dependências sob demanda (lazy loading):

- **`obter_token_adapta()`**: Executa `extract_token.js` via `subprocess` para obter o token JWT do Adapta ONE
- **`verificar_token_expirado(token)`**: Decodifica o payload Base64 do JWT e verifica se expira em menos de 60 segundos
- **`renovar_token()`**: Tenta abrir o app Adapta ONE Desktop em modo oculto e aguarda até 12s por um novo token
- **`verificar_cliente_planilha(polo_a, numero_processo)`**: Consulta a planilha Excel e retorna `{'e_nosso': bool, 'cliente_planilha': str, 'contrario': str}`

### `adapters/web/driver_setup.py` — Configuração do Chrome

- Detecta a versão do Chrome instalado via Windows Registry (`HKCU` ou `HKLM`)
- Tenta usar `undetected_chromedriver` (prioridade) ou fallback para Selenium padrão
- Opções anti-detecção: `--disable-blink-features=AutomationControlled`, user-agent customizado
- Fallback de versão: 148 (se não conseguir detectar)

### `adapters/web/scraper.py` — Extração de Dados

- **`parse_conteudo_dinamico(texto)`**: Parser regex que extrai campos chave-valor, advogados (nome + OAB) e flags (sigiloso, autos digitais)
- **`_extrair_numero_cnj(texto, driver)`**: Tenta múltiplos padrões regex para encontrar o número CNJ, incluindo conversão de "Número Único" (20 dígitos) para formato CNJ
- **`raspar_detalhes_publicacao(driver)`**: Coleta conteúdo, fonte do tribunal, data de disponibilização, badge e tipo

### `adapters/web/acoes.py` — Ações no Sistema

- **`marcar_sem_providencia(driver)`**: Abre dropdown de status → seleciona "Sem providências" (múltiplos XPaths de fallback)
- **`clicar_link_processo(driver, dados, adapta_info)`**: Fluxo complexo que:
  1. Clica no link do processo (abre nova aba)
  2. Navega para aba "Compromissos e tarefas"
  3. Clica em "Adicionar" → "Novo compromisso"
  4. Abre lookup de descrição
  5. Coleta todas as opções disponíveis (até 5 páginas)
  6. Envia opções para IA classificar a melhor descrição
  7. Seleciona a opção classificada no lookup
  8. Retorna para a aba original

### `adapters/ia/adapta_one_cliente.py` — Cliente Adapta ONE

- **`analisar(pub, lado)`**: Monta um prompt estruturado com dados da publicação e envia via streaming para `https://agent.adapta.one/api/chat/stream/v1`
- **`_localizar_expert()`**: Busca o expert "o processualista v2" na lista de experts do Adapta ONE
- **`_enviar_mensagem(text)`**: Envia mensagem via SSE streaming, ignora chunks `reasoning-delta`, monta resposta completa
- **Fallback**: Se a IA falhar, retorna análise offline com prazo padrão de 15 dias

### `core/services/calcular_prazo.py` — Cálculo de Prazos

```python
MULTIPLICADOR_DIAS_UTEIS = 1.4   # Conversão dias corridos → dias úteis
ANTECEDENCIA_DIAS = 5            # Margem antes do prazo

data_limite = data_disponibilizacao + (dias_uteis × 1.4)
data_agendamento = data_limite - 5 dias

# Classificação:
# data_agendamento < hoje         → ATRASADO
# dias_restantes <= 2             → URGENTE
# caso contrário                  → OK
```

### `adapters/persistencia/json_repositorio.py` — Persistência

- Salva/atualiza publicações em `dados/publicacoes.json` (upsert por `processo_numero`)
- Se `processo_numero` é "N/A", gera um ID temporário via MD5 do conteúdo
- **`gerar_relatorio()`**: Gera `dados/relatorio_analise.json` com:
  - `nosso_tratado`: publicações do escritório já marcadas como "Tratado"
  - `pendentes_acao`: publicações do escritório ainda pendentes
  - `operadora_sem_providencia`: publicações da operadora marcadas
  - `urgencias_nossas`: processos com status URGENTE ou ATRASADO

---

## Arquivos de Saída

### `dados/publicacoes.json`

Array de objetos JSON, cada um representando uma publicação processada:

```json
{
  "url_pagina": "https://firm.legalone.com.br/...",
  "data_raspagem": "2025-01-15T14:30:00",
  "processo_numero": "0001234-56.2024.8.26.0100",
  "tipo": "Despacho",
  "data_disponibilizacao": "2025-01-10",
  "fonte_tribunal": "TJSP",
  "conteudo": "texto completo da publicação...",
  "lado_processo": "nosso_cliente",
  "analise_gemini": {
    "resumo": "Resumo da análise...",
    "urgencia": "MEDIA",
    "prazo_recomendado_dias_uteis": 15
  },
  "agendamento": {
    "data_limite": "30/01/2025",
    "data_agendamento": "25/01/2025",
    "status_temporal": "OK",
    "dias_restantes": 10
  },
  "acao_executada": "Tratado",
  "decisao_agendamento": "AGENDAR"
}
```

### `dados/relatorio_analise.json`

```json
{
  "timestamp": "2025-01-15T15:00:00",
  "total": 25,
  "com_analise": 23,
  "sem_analise": 2,
  "nosso_tratado": [...],
  "pendentes_acao": [...],
  "operadora_sem_providencia": [...],
  "urgencias_nossas": [...]
}
```

### `screenshots_debug/` e `debug_html/`

Diretórios de diagnóstico auto-gerados:
- **`pos_login.png`**: Screenshot pós-login
- **`pos_publicacoes.png`**: Screenshot pós-navegação
- **`erro_fatal_v2.png`**: Screenshot ao erro fatal
- **`debug_dropdown_nao_encontrado.png`**: Falha ao abrir dropdown de status
- **`<contexto>.html`**: HTML completo da página no momento do diagnóstico

---

## Solução de Problemas

### Login falha

- Verifique `THOMSON_USERNAME` e `THOMSON_PASSWORD` no `.env`
- O Legal One pode estar fora ou com manutenção — acesse manualmente para confirmar
- Tempo limite padrão: 20s (login) + 30s (pós-login)

### Chrome não inicia

- Verifique se o Google Chrome está instalado
- O `undetected-chromedriver` baixa o chromedriver automaticamente, mas pode falhar se a versão do Chrome for muito recente
- Fallback: desinstale `undetected-chromedriver` e use Selenium padrão

### Token Adapta ONE não obtido

- O app **Adapta ONE Desktop** precisa estar instalado e com sessão ativa
- O `extract_token.js` lê o arquivo `%APPDATA%\AdaptaONE\auth-session.enc` (Windows)
- Se o token expirar, o sistema tenta renovar automaticamente abrindo o app
- Use `--sem-adapta` para pular a integração com IA

### Publicações não aparecem

- A planilha Excel precisa estar no caminho correto: `../Automação publicação Juridico/`
- O filtro de responsável está hardcoded como "Aline Frutuoso" — altere em `settings.py` se necessário
- O período de filtro é fixo em 60 dias

### Erros de scraping

- O Legal One é um SPA (Single Page Application) — o código usa vários `time.sleep()` para aguardar carregamento
- Screenshots de diagnóstico são salvos em `screenshots_debug/` e HTMLs em `debug_html/`
- Se o layout do Legal One mudar, os seletores CSS/XPath em `navegacao.py`, `scraper.py` e `acoes.py` precisarão de atualização

### Plano de fundo: Multiplicador 1.4x

O cálculo de prazos usa `dias_uteis × 1.4` para converter dias úteis em dias corridos (considerando fins de semana). Isso significa que 15 dias úteis ≈ 21 dias corridos.
