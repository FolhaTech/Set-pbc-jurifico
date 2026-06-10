"""
run_v2.py — Ponto de entrada (Hexagonal / Ports & Adapters)
===========================================================

Uso:
  python run_v2.py                      -> Processa a primeira publicacao
  python run_v2.py --todas              -> Processa TODAS as publicacoes
  python run_v2.py --sem-adapta         -> Modo offline (sem IA)
  python run_v2.py --todas --sem-adapta -> Todas em modo offline
  python run_v2.py --max 10             -> Limite de publicacoes
"""

import sys
import logging
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from config.settings import MAX_PUBLICACOES
from config.di import Container, verificar_cliente_planilha
from adapters.infra.logging_utils import configurar_logging, salvar_screenshot, diagnosticar_pagina


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automacao de Publicacoes Juridicas — Legal One (v2 Hexagonal)"
    )
    parser.add_argument(
        "--todas", action="store_true",
        help="Processa todas as publicacoes (padrao: apenas a primeira)",
    )
    parser.add_argument(
        "--sem-adapta", action="store_true",
        help="Desativa o envio ao Adapta ONE (ativo por padrao)",
    )
    parser.add_argument(
        "--max", type=int, default=MAX_PUBLICACOES,
        help=f"Numero maximo de publicacoes (padrao: {MAX_PUBLICACOES})",
    )
    args = parser.parse_args()
    usar_ia = not args.sem_adapta

    configurar_logging()

    print("\n" + "=" * 70)
    print("  AUTOMACAO DE PUBLICACOES JURIDICAS — Legal One (v2 Hexagonal)")
    print(f"  Modo: {'Todas as publicacoes' if args.todas else 'Primeira publicacao'}")
    print(f"  IA:   {'Adapta ONE ativa' if usar_ia else 'Offline (apenas planilha)'}")
    print("=" * 70 + "\n")

    container = Container(usar_ia=usar_ia)

    try:
        nav = container.navegador

        logging.info("[V2] 1/4 — Login no Legal One...")
        nav.login()

        logging.info("[V2] 2/4 — Navegando para Publicacoes...")
        nav.navegar_para_publicacoes()

        logging.info("[V2] 3/4 — Aplicando filtros...")
        nav.aplicar_filtros()

        logging.info("[V2] 4/4 — Processando publicacoes...")
        if args.todas:
            caso = container.criar_processar_lista(
                max_publicacoes=args.max,
                verificacao_planilha=verificar_cliente_planilha,
            )
            total = caso.executar_todas()
            logging.info(f"[V2] Concluido — {total} publicacoes processadas.")
        else:
            caso = container.criar_analisar_publicacao()
            pub = nav.raspar_proxima_publicacao()
            if pub:
                resultado = verificar_cliente_planilha(
                    polo_a=pub.conteudo_parsed.campos.get("polo_a", ""),
                    numero_processo=pub.processo_numero,
                )
                caso.executar(pub, e_nosso=resultado["e_nosso"])
                container.repositorio.salvar(pub)
                logging.info("[V2] Primeira publicacao processada.")

        relatorio = container.repositorio.gerar_relatorio()
        logging.info(
            f"[V2] Relatorio gerado — "
            f"{len(relatorio.get('nosso_tratado', []))} tratados | "
            f"{len(relatorio.get('pendentes_acao', []))} pendentes | "
            f"{len(relatorio.get('operadora_sem_providencia', []))} sem providencia"
        )

        logging.info("[V2] Automacao concluida com sucesso!")

    except KeyboardInterrupt:
        logging.warning("\n[V2] Interrompido pelo usuario (Ctrl+C).")

    except Exception as e:
        logging.error(f"[V2] Erro fatal: {e}")
        try:
            salvar_screenshot(container.navegador.driver, "erro_fatal_v2")
            diagnosticar_pagina(container.navegador.driver, "erro_fatal_v2")
        except Exception:
            pass

    finally:
        container.fechar()
        logging.info("[V2] Driver encerrado.")


if __name__ == "__main__":
    main()
