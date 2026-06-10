from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from core.enums import StatusTemporal, LadoProcesso, Urgencia, StatusAcao


@dataclass
class Advogado:
    nome: str
    oab: str


@dataclass
class FlagsPublicacao:
    eh_sigiloso: bool = False
    processo_sigiloso: bool = False
    consulta_autos_digitais: bool = False


@dataclass
class ConteudoParsed:
    campos: dict = field(default_factory=dict)
    advogados: list[Advogado] = field(default_factory=list)
    flags: FlagsPublicacao = field(default_factory=FlagsPublicacao)
    texto_bruto: str = ""


@dataclass
class Agendamento:
    data_limite: date
    data_agendamento: date
    status_temporal: StatusTemporal
    dias_restantes: int


@dataclass
class Analise:
    lado: LadoProcesso
    resumo: str
    urgencia: Urgencia
    prazo_dias: int
    acao_recomendada: str
    requer_acao: bool
    fonte_ia: str
    analise_completa: Optional[str] = None
    agendamento: Optional[Agendamento] = None
    decisao_agendamento: Optional[str] = None
    status_acao: StatusAcao = StatusAcao.PENDENTE


@dataclass
class Publicacao:
    url_pagina: str
    data_raspagem: datetime
    processo_numero: str
    processo_href: Optional[str] = None
    tipo: str = "N/A"
    badge: str = "N/A"
    data_disponibilizacao: Optional[date] = None
    fonte_tribunal: str = "N/A"
    fonte_diario: str = "N/A"
    conteudo: str = ""
    conteudo_parsed: ConteudoParsed = field(default_factory=ConteudoParsed)
    analise: Optional[Analise] = None
