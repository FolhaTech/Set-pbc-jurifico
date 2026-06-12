from datetime import date, timedelta

from core.entities import Agendamento
from core.enums import StatusTemporal


class CalcularPrazo:
    ANTECEDENCIA_DIAS = 5
    MULTIPLICADOR_DIAS_UTEIS = 1.4

    def calcular_prazo(self, dias_uteis: int, data_disponivel: date) -> Agendamento:
        hoje = date.today()
        data_limite = data_disponivel + timedelta(
            days=dias_uteis * self.MULTIPLICADOR_DIAS_UTEIS
        )

        data_agendamento = data_limite - timedelta(days=self.ANTECEDENCIA_DIAS)
        dias_restantes = (data_agendamento - hoje).days

        if data_agendamento < hoje:
            status_temporal = StatusTemporal.ATRASADO
        elif dias_restantes <= 2:
            status_temporal = StatusTemporal.URGENTE
        else:
            status_temporal = StatusTemporal.OK

        return Agendamento(
            data_limite=data_limite,
            data_agendamento=data_agendamento,
            status_temporal=status_temporal,
            dias_restantes=dias_restantes,
        )

    def calcular_prazo_solicitado_juiz(self, data_solicitada: date) -> Agendamento:
        hoje = date.today()
        data_agendamento = data_solicitada - timedelta(days=self.ANTECEDENCIA_DIAS)
        dias_restantes = (data_agendamento - hoje).days

        if data_agendamento < hoje:
            status_temporal = StatusTemporal.ATRASADO
        elif dias_restantes <= 2:
            status_temporal = StatusTemporal.URGENTE
        else:
            status_temporal = StatusTemporal.OK

        return Agendamento(
            data_limite=data_solicitada,
            data_agendamento=data_agendamento,
            status_temporal=status_temporal,
            dias_restantes=dias_restantes,
        )
