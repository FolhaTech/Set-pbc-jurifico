from enum import Enum


class LadoProcesso(Enum):
    NOSSO_CLIENTE = "nosso_cliente"
    OPERADORA = "operadora"


class StatusTemporal(Enum):
    OK = "OK"
    URGENTE = "URGENTE"
    ATRASADO = "ATRASADO"


class Urgencia(Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"


class StatusAcao(Enum):
    SEM_PROVIDENCIA = "Sem providencia"
    PENDENTE = "Pendente revisao manual"
    TRATADO = "Tratado"
    FALHA = "Falha ao marcar"
